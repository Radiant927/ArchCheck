import json
import warnings
import numpy as np
from collections import defaultdict
from pathlib import Path
from core.config import DATA
from core import i18n
from core.i18n import set_language, _floor_label
from kb import steward
from risk.families import get_family
from risk.adapter import (maintenance_available, monitoring_measurements,
                          population_from_building)
from risk.survival import fit_cox, predict
from risk.evaluate import data_sufficiency

HERE = Path(__file__).resolve().parent.parent

CIVIL_RULES = []
EEE_RULES = []
BUILDING_RULES = []
STRUCTURAL_RULES = []
MEP_RULES = []
ACCESSIBILITY_RULES = []
STD_META = {}

# 每个类别默认判定的元素作用域；规则可用 "scope" 字段声明自己属于哪类元素，
# 引擎据此只把它喂给正确的元素（防止"房间规则"跑到"分区"上报假缺字段）。
_DEFAULT_SCOPE = {"civil": "room", "eee": "equipment", "structural": "structure",
                  "mep": "pipe", "building": "building", "accessibility": "room"}

# 这些作用域的元素是真实物理构件（有可被 3D viewer 拾取的 GlobalId），
# 违规时可直接高亮该构件本身；room/zone/building 则退回"房间内构件"兜底定位。
_PHYSICAL_SCOPES = {"structure", "pipe", "duct", "equipment"}

def load_standard(standard_id):
    """Load rules + meta for a given standard (cn / sg)."""
    base = DATA / "standards" / standard_id
    fallback = {"civil": [], "eee": [], "building": [], "structural": [], "mep": [],
                "accessibility": [], "meta": {}}
    result = dict(fallback)
    for key, fname in [("civil", "civil_rules.json"), ("eee", "eee_rules.json"),
                       ("building", "building_rules.json"),
                       ("structural", "structural_rules.json"),
                       ("mep", "mep_rules.json"),
                       ("accessibility", "accessibility_rules.json"),
                       ("meta", "meta.json")]:
        p = base / fname
        if p.exists():
            try:
                result[key] = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return result

def list_standards():
    """[(id, meta)] for every standard directory under data/standards/.

    Adding a new standard is a config-only change: drop data/standards/<code>/
    with meta.json + rule files and it appears in the sidebar automatically.
    """
    out = []
    if DATA.exists():
        for d in sorted((DATA / "standards").glob("*")):
            if not d.is_dir():
                continue
            meta = {}
            mp = d / "meta.json"
            if mp.exists():
                try:
                    meta = json.loads(mp.read_text(encoding="utf-8"))
                except Exception:
                    pass
            out.append((d.name, meta))
    return out

def load_demo_data():
    p = DATA / "demo_building_data.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"project_name": "Demo", "building_params": {}, "floors": []}

DEMO_DATA = load_demo_data()

def set_standard(standard_id):
    """Load a standard's rules + meta and switch the UI language."""
    global CIVIL_RULES, EEE_RULES, BUILDING_RULES, STRUCTURAL_RULES, MEP_RULES, STD_META
    global ACCESSIBILITY_RULES
    std = load_standard(standard_id)
    CIVIL_RULES = std["civil"]
    EEE_RULES = std["eee"]
    BUILDING_RULES = std["building"]
    STRUCTURAL_RULES = std["structural"]
    MEP_RULES = std["mep"]
    ACCESSIBILITY_RULES = std["accessibility"]
    STD_META = std["meta"]
    set_language(STD_META.get("language", "en"))
    return std

OPERATORS = {
    "<=": lambda a,b: a<=b, ">=": lambda a,b: a>=b, ">": lambda a,b: a>b,
    "<": lambda a,b: a<b, "==": lambda a,b: a==b, "!=": lambda a,b: a!=b,
    "in": lambda a,b: a in b, "not_in": lambda a,b: a not in b,
}

def _rule_applies(rule, item):
    """Whether a rule's condition would let it judge this item."""
    cf = rule.get("condition_field")
    if cf:
        cv = item.get(cf)
        if cv is None:
            return False  # filter field absent -> cannot confirm applicability -> skip (avoid noise)
        if not OPERATORS[rule["condition_operator"]](cv, rule["condition_threshold"]):
            return False
    # Optional AND-ed applicability filters, e.g. STR-001 excluding non-concrete
    # columns: "conditions_all": [{"field": "material_class", "operator": "not_in",
    #                              "threshold": ["wood","steel","masonry"]}].
    # A clause whose field is ABSENT from the item is ignored (not failed), so
    # older / demo data without the enriched field behaves exactly as before.
    for cond in rule.get("conditions_all", []) or []:
        fld = cond.get("field")
        if not fld or fld not in item:
            continue
        op = OPERATORS[cond["operator"]]
        if not op(item[fld], cond["threshold"]):
            return False
    return True


def _arbitration_tag(rule):
    """Tag for a finding whose rule needs AI arbitration before it is final.

    Returns a dict {pending, point, description, candidates, target_field}
    when the rule carries an ``arbitration`` block with ``required`` true,
    otherwise None. The finding still appears in the deterministic result —
    the tag only marks it as "AI suggestion awaiting human confirmation".
    """
    arb = rule.get("arbitration") or {}
    if not arb.get("required"):
        return None
    return {
        "pending": True,
        "point": arb.get("point"),
        "description": arb.get("description", ""),
        "candidates": arb.get("candidates", []),
        "target_field": arb.get("target_field", "threshold"),
        "rag_query": arb.get("rag_query", ""),
    }


def run_rules(rules, item, prefix, scope, floor_id=None, floor_name=None, coverage=None,
              tally=None):
    """Run a rule set against one item.

    ``scope`` is the element type being judged (room / zone / equipment / structure /
    pipe / duct / building). A rule may declare its own ``scope``; rules whose scope
    does not match are skipped entirely so they never report a spurious missing-field
    gap on the wrong element type.

    When a rule applies to the item but the judged field is absent from the model,
    it is recorded into ``coverage`` (rule_id -> stats) instead of silently skipped —
    this is what turns "dead rules" into an honest "未检查（缺字段）" report.

    ``tally`` counts, per rule, how many items were actually judged vs. had a null
    value, so ``run_full_review`` can tell a rule-level gap (nothing judged) from
    per-item data defects (some judged) and aggregate only the former.
    """
    violations = []
    default_scope = _DEFAULT_SCOPE.get(prefix, "room")
    for rule in rules:
        if rule.get("scope", default_scope) != scope:
            continue
        if rule.get("kind") == "predictive":
            # predictive rules run through run_predictive_review, never the
            # field/threshold path (they have no "field" entry).
            continue
        field = rule["field"]
        # Tally is created up front (before the condition filter) so a rule whose
        # condition matches nothing still shows up as "matched 0" — the honest
        # signal that the model lacks the qualifying elements (e.g. a fire-pipe
        # rule on a model with pipes but no fire pipes).
        if tally is not None:
            t = tally.setdefault(rule["id"], {
                "title": rule["name"], "code_ref": rule["code_ref"], "field": field,
                "prefix": prefix, "judged": 0, "null": 0, "matched": 0, "locations": [],
            })
        else:
            t = None
        cond_passes = _rule_applies(rule, item)
        if t is not None and cond_passes:
            t["matched"] += 1
        if not cond_passes:
            continue
        if field not in item:
            if coverage is not None:
                rid = rule["id"]
                c = coverage.setdefault(rid, {
                    "title": rule["name"], "code_ref": rule["code_ref"],
                    "field": field, "count": 0, "locations": [], "prefix": prefix,
                })
                c["count"] += 1
                loc = item.get("name", item.get("id", "?"))
                if len(c["locations"]) < 5 and loc not in c["locations"]:
                    c["locations"].append(str(loc))
            continue
        value = None
        # condition filter FIRST — skip items the rule doesn't apply to (e.g. a
        # drainage rule on an unknown pipe) even when the field itself is None,
        # so non-matching items don't produce spurious "data missing" findings.
        value = item[field]
        room_name = item.get("name", item.get("id", "?"))
        # 构件级精确定位：物理构件类规则（结构/管道/风管/设备）带上元素 GlobalId，
        # 供 3D viewer 精确高亮单个构件；房间/全楼规则不带（房间改用房间内构件兜底）。
        _item_gid = item.get("global_id") or item.get("id") or ""
        _eids = [_item_gid] if (_item_gid and scope in _PHYSICAL_SCOPES) else []
        if value is None:
            if t is not None:
                t["null"] += 1
                if len(t["locations"]) < 5 and str(room_name) not in t["locations"]:
                    t["locations"].append(str(room_name))
            violations.append({
                "title": rule["name"],
                "description": i18n._I18N[i18n.LANG]["rule_data_missing"].format(field=field),
                "location": room_name, "severity": "Missing",
                "code_ref": rule["code_ref"], "type": prefix,
                "rule_id": rule["id"],
                "floor_id": floor_id,
                "floor_name": floor_name,
                "element_global_ids": _eids,
            })
            continue
        if t is not None:
            t["judged"] += 1
        threshold = steward.resolve_threshold(rule, item)
        op_func = OPERATORS[rule["operator"]]
        if op_func(value, threshold):
            continue
        cond_field = rule.get("condition_field")
        cond_value = item.get(cond_field) if cond_field else None
        cond_threshold = rule.get("condition_threshold")
        msg = rule["message"].replace("{value}", str(value)).replace("{threshold}", str(threshold)).replace("{room_name}", str(room_name))
        if cond_value is not None and "{condition_value}" in msg:
            msg = msg.replace("{condition_value}", str(cond_value)).replace("{condition_threshold}", str(cond_threshold))
        _dyn = rule.get("dynamic_threshold") or {}
        if _dyn.get("formula"):
            msg += f" （{i18n._I18N[i18n.LANG]['formula_lbl']}：{_dyn['formula']}）" if i18n.LANG == "zh" \
                else f" ({i18n._I18N[i18n.LANG]['formula_lbl']}: {_dyn['formula']})"
        violations.append({
            "title": rule["name"], "description": msg,
            "location": room_name, "severity": rule["severity"],
            "code_ref": rule["code_ref"], "type": prefix,
            "rule_id": rule["id"],
            "floor_id": floor_id,
            "floor_name": floor_name,
            "element_global_ids": _eids,
            "arbitration": _arbitration_tag(rule),
        })
    return violations

_SCOPE_LABEL = {"room": "房间", "zone": "防火分区", "equipment": "电气设备",
                "structure": "结构构件", "pipe": "管道", "duct": "风管", "building": "全楼"}


def find_rule(rule_id):
    """Look up a rule dict by id across all loaded rule sets (None if absent)."""
    for ruleset in (CIVIL_RULES, EEE_RULES, BUILDING_RULES, STRUCTURAL_RULES,
                    MEP_RULES, ACCESSIBILITY_RULES):
        for r in ruleset:
            if r.get("id") == rule_id:
                return r
    return None


def arbitrate_finding(finding, rule, bdata):
    """Run AI arbitration for one finding whose rule needs it.

    Builds the project context from ``bdata`` and the finding, then delegates
    to the Arbitration agent. Returns the suggestion dict, or None when the
    rule has no arbitration block. Never raises — the agent degrades
    gracefully when the LLM / RAG is unavailable.
    """
    if not (rule.get("arbitration") or {}).get("required"):
        return None

    floors = bdata.get("floors", [])
    total_area = 0.0
    for f in floors:
        for r in f.get("rooms", []):
            total_area += float(r.get("room_area_sqm") or 0)
    btype = bdata.get("building_type") or bdata.get("btype") or "未标注"

    # locate the element the finding is about (room name match within its floor)
    element = {"名称": finding.get("location", "?")}
    for f in floors:
        if f.get("floor_id") != finding.get("floor_id"):
            continue
        for r in f.get("rooms", []):
            if str(r.get("name", "")) == str(finding.get("location", "")):
                element["房间面积_m²"] = r.get("room_area_sqm")
                element["房间类型"] = r.get("type")
                for k in ("corridor_length_m", "exit_count", "door_width_m",
                          "max_room_travel_dist_m", "room_area_sqm", "has_sprinkler"):
                    if r.get(k) is not None:
                        element[k] = r.get(k)
                break

    context = {
        "building": {
            "type": btype,
            "num_floors": len(floors),
            "total_area_m2": round(total_area, 1),
        },
        "element": element,
        "std_name": STD_META.get("short_name", "?"),
        "lang": i18n.LANG,
    }

    try:
        from agents import arbitrator as ARB
        return ARB.arbitrate(rule, context)
    except Exception:
        return None



def _predictive_notchecked(rule, description):
    return {
        "title": f'{rule["name"]}（未检查）',
        "description": description,
        "location": "—", "severity": "NotChecked",
        "code_ref": rule.get("code_ref", ""),
        "type": "mep", "rule_id": rule["id"], "floor_name": None,
    }


def _pipe_index(bdata):
    """global_id -> (pipe name, floor_id, floor_name) for all extracted pipes."""
    out = {}
    for fl in bdata.get("floors", []):
        fid = fl.get("floor_id", "")
        fname = fl.get("name")
        for p in fl.get("pipes", []):
            gid = p.get("global_id")
            if gid:
                out[gid] = (p.get("name", gid), fid, fname)
    return out


def run_predictive_review(bdata, rules):
    """Predictive rule layer: survival-model warnings + ranked inspection list.

    One fit per ``family`` declared by the ``kind="predictive"`` rules. When
    maintenance inputs are absent, unmatchable, or below the data-sufficiency
    gate, each rule produces one NotChecked coverage finding instead of a
    prediction — no number is ever fabricated from a geometry-only model.

    Returns ``(issues, coverage_findings, ranking, monitor)``; ``ranking`` rows
    carry rank / global_id / location / floor_name / p_fail_cycle /
    median_failure_year, sorted by within-cycle failure probability.
    ``monitor`` is ``{}`` when no monitoring data was consumed, otherwise
    ``{"regime": "inspection"|"sensor", "n_modeled": int}``.
    """
    pred_rules = [r for r in rules if r.get("kind") == "predictive"]
    if not pred_rules:
        return [], [], [], []

    t = i18n._I18N[i18n.LANG]
    issues, coverage, ranking = [], [], []
    monitor = {}
    by_family = defaultdict(list)
    for rule in pred_rules:
        by_family[rule.get("family", "steel_pipe")].append(rule)

    for family_name, frules in by_family.items():
        try:
            family = get_family(family_name)
        except KeyError:
            for rule in frules:
                coverage.append(_predictive_notchecked(
                    rule, t["predictive_nodata_desc"]))
            continue

        if (not maintenance_available(bdata)
                or population_from_building(bdata, family) is None):
            for rule in frules:
                coverage.append(_predictive_notchecked(
                    rule, t["predictive_nodata_desc"]))
            continue

        pop, _meta = population_from_building(bdata, family)
        # Optional monitoring covariates (wall-thickness readings). Absent data
        # leaves the fit on static covariates, exactly as before; unusable data
        # abstains rather than pretending the pipes are unmonitored.
        meas, mon = monitoring_measurements(bdata, family, pop)
        if mon["status"] == "invalid":
            for rule in frules:
                coverage.append(_predictive_notchecked(
                    rule, t["predictive_monitoring_invalid_desc"]))
            continue
        if mon["status"] == "incomplete":
            desc = t["predictive_monitoring_incomplete_desc"].format(
                covered=mon["covered"], modeled=mon["modeled"])
            for rule in frules:
                coverage.append(_predictive_notchecked(rule, desc))
            continue

        gate = data_sufficiency(pop, family,
                                extra_columns=1 if meas is not None else 0)
        if not gate["sufficient"]:
            desc = t["predictive_insufficient_desc"].format(
                reasons="；".join(gate["reasons"]))
            for rule in frules:
                coverage.append(_predictive_notchecked(rule, desc))
            continue

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cox = fit_cox(pop, family, measurements=meas)
            converged = bool(np.isfinite(cox.beta).all())
            pr = predict(cox, pop, measurements=meas) if converged else None
        if not converged:
            for rule in frules:
                coverage.append(_predictive_notchecked(
                    rule, t["predictive_unconverged_desc"]))
            continue
        if meas is not None:
            monitor = {"regime": mon.get("regime"),
                       "n_modeled": mon.get("n_modeled")}

        idx = _pipe_index(bdata)
        cycle = int(family["inspection_cycle_years"])
        for rule in frules:
            threshold = float(rule.get("prob_threshold", 0.5))
            for row in pr.itertuples(index=False):
                p = float(row.p_fail_cycle)
                if p < threshold:
                    continue
                gid = row.comp_id
                loc, fid, fname = idx.get(gid, (gid, None, None))
                median = (None if not np.isfinite(row.median_failure_year)
                          else round(float(row.median_failure_year), 1))
                desc = t["predictive_warning_desc"].format(
                    cycle=cycle, prob=f"{p:.0%}",
                    median=(median if median is not None else "—"))
                issues.append({
                    "title": rule["name"], "description": desc,
                    "location": loc, "severity": "Predictive",
                    "code_ref": rule.get("code_ref", ""), "type": "mep",
                    "rule_id": rule["id"], "floor_id": fid,
                    "floor_name": fname,
                    "element_global_ids": [gid],
                })

        order = pr.sort_values("p_fail_cycle", ascending=False)
        for rank_i, row in enumerate(order.itertuples(index=False), 1):
            gid = row.comp_id
            loc, _fid, fname = idx.get(gid, (gid, None, None))
            median = (None if not np.isfinite(row.median_failure_year)
                      else round(float(row.median_failure_year), 1))
            ranking.append({
                "rank": rank_i, "global_id": gid, "location": loc,
                "floor_name": fname,
                "p_fail_cycle": round(float(row.p_fail_cycle), 3),
                "median_failure_year": median,
            })

    return issues, coverage, ranking, monitor


def run_full_review(bdata):
    civil_results = []
    eee_results = []
    building_results = []
    structural_results = []
    mep_results = []
    accessibility_results = []
    coverage = {}
    tally = {}
    scope_counts = defaultdict(int)
    # how many items each discipline actually judged (0 -> "not checked")
    checked = {"civil": 0, "eee": 0, "structural": 0, "mep": 0, "building": 0,
               "accessibility": 0}

    for floor in bdata.get("floors", []):
        fid = floor.get("floor_id", "")
        fname = _floor_label(floor.get("floor_name", fid))
        rooms = floor.get("rooms", [])
        for room in rooms:
            checked["civil"] += 1
            checked["accessibility"] += 1
            scope_counts["room"] += 1
            civil_results.extend(run_rules(CIVIL_RULES, room, "civil", "room", fid, fname, coverage, tally))
            accessibility_results.extend(run_rules(ACCESSIBILITY_RULES, room, "accessibility", "room", fid, fname, coverage, tally))
        eqs = floor.get("electrical_elements", [])
        checked["eee"] += len(eqs)
        scope_counts["equipment"] += len(eqs)
        for eq in eqs:
            eee_results.extend(run_rules(EEE_RULES, eq, "eee", "equipment", fid, fname, coverage, tally))
        zones = floor.get("fire_zones", [])
        scope_counts["zone"] += len(zones)
        for zone in zones:
            checked["civil"] += 1
            civil_results.extend(run_rules(CIVIL_RULES, zone, "civil", "zone", fid, fname, coverage, tally))
        elems = floor.get("structural_elements", [])
        checked["structural"] += len(elems)
        scope_counts["structure"] += len(elems)
        for elem in elems:
            structural_results.extend(run_rules(STRUCTURAL_RULES, elem, "structural", "structure", fid, fname, coverage, tally))
        pipes = floor.get("pipes", [])
        ducts = floor.get("ducts", [])
        checked["mep"] += sum(1 for p in pipes if p.get("pipe_type") not in ("unknown",)) + len(ducts)
        scope_counts["pipe"] += len(pipes)
        scope_counts["duct"] += len(ducts)
        for pipe in pipes:
            mep_results.extend(run_rules(MEP_RULES, pipe, "mep", "pipe", fid, fname, coverage, tally))
        for duct in ducts:
            mep_results.extend(run_rules(MEP_RULES, duct, "mep", "duct", fid, fname, coverage, tally))

    bp = bdata.get("building_params", {})
    whole_label = i18n._I18N[i18n.LANG]["whole_building"]
    checked["building"] = 1
    scope_counts["building"] += 1
    building_results.extend(run_rules(BUILDING_RULES, bp, "building", "building", None, whole_label, coverage, tally))
    accessibility_results.extend(run_rules(ACCESSIBILITY_RULES, bp, "accessibility", "building", None, whole_label, coverage, tally))

    # predictive layer (Cox survival on maintenance records; abstains honestly)
    (predictive_results, predictive_coverage,
     predictive_ranking, predictive_monitor) = run_predictive_review(
        bdata, MEP_RULES)

    # A rule whose field exists but is null on *every* element it applied to is a
    # rule-level gap, not N per-element defects — collapse it into the coverage
    # report so a discipline-only model (e.g. an MEP-only file with no doors at all)
    # does not flood the list with 42 identical "data missing" rows. Partial gaps
    # stay per-element: those name the specific rooms worth fixing.
    collapsed = {rid: t for rid, t in tally.items() if t["judged"] == 0 and t["null"] > 0}
    if collapsed:
        for lst in (civil_results, eee_results, building_results,
                    structural_results, mep_results, accessibility_results):
            lst[:] = [f for f in lst
                      if not (f.get("severity") == "Missing" and f.get("rule_id") in collapsed)]

    # coverage report — rules that exist but could not judge because the model
    # lacks their field (per-rule aggregation) or their element scope entirely.
    coverage_findings = []
    empty_scope_rules = defaultdict(list)
    for rid, t in collapsed.items():
        if rid in coverage:
            coverage[rid]["count"] += t["null"]
            continue
        coverage_findings.append({
            "title": f'{t["title"]}（未检查）',
            "description": (f'模型提取到字段 {t["field"]} 但所有 {t["null"]} 个元素都没有值，'
                            f'无一可判定。补齐该字段的取值后规则将自动启用。'),
            "location": "、".join(t["locations"]) or "—",
            "severity": "NotChecked",
            "code_ref": t["code_ref"],
            "type": t["prefix"],
            "rule_id": rid,
            "floor_name": None,
        })
    for rid, c in coverage.items():
        loc = "、".join(c["locations"]) or "—"
        coverage_findings.append({
            "title": f'{c["title"]}（未检查）',
            "description": (f'规则因模型缺少字段 {c["field"]} 无法判定（影响 {c["count"]} 个元素）。'
                            f'模型补充该字段后规则将自动启用。'),
            "location": loc,
            "severity": "NotChecked",
            "code_ref": c["code_ref"],
            "type": c["prefix"],
            "rule_id": rid,
            "floor_name": None,
        })
    for prefix, rules in [("civil", CIVIL_RULES), ("eee", EEE_RULES),
                          ("structural", STRUCTURAL_RULES), ("mep", MEP_RULES),
                          ("building", BUILDING_RULES), ("accessibility", ACCESSIBILITY_RULES)]:
        default_scope = _DEFAULT_SCOPE.get(prefix, "room")
        for rule in rules:
            if rule.get("kind") == "predictive":
                continue  # abstention handled by run_predictive_review
            rscope = rule.get("scope", default_scope)
            if scope_counts[rscope] == 0 and rule["id"] not in coverage:
                empty_scope_rules[rscope].append((rule["id"], rule["name"], rule["code_ref"], prefix))
    for rscope, items in sorted(empty_scope_rules.items()):
        lbl = _SCOPE_LABEL.get(rscope, rscope)
        n = len(items)
        names = "、".join(name for _, name, _, _ in items[:4])
        coverage_findings.append({
            "title": f"{n} 条规则需 {lbl} 数据（未检查）",
            "description": (f"模型中没有 {lbl} 元素，以下 {n} 条规则无法判定：{names}"
                            f"{'等' if n > 4 else ''}。提取该类型数据后规则将自动启用。"),
            "location": "—",
            "severity": "NotChecked",
            "code_ref": items[0][2],
            "type": items[0][3],
            "rule_id": f"scope::{rscope}",
            "floor_name": None,
        })

    # A rule whose condition matched 0 elements (e.g. MEP-009 fire-pipe rule on a
    # model that has pipes but zero fire pipes) would silently judge nothing and
    # the demo would mislabel it "全部通过" — surface it as 未检查 instead.
    for prefix, rules in [("civil", CIVIL_RULES), ("eee", EEE_RULES),
                          ("structural", STRUCTURAL_RULES), ("mep", MEP_RULES),
                          ("building", BUILDING_RULES), ("accessibility", ACCESSIBILITY_RULES)]:
        default_scope = _DEFAULT_SCOPE.get(prefix, "room")
        for rule in rules:
            if rule.get("kind") == "predictive":
                continue
            rid = rule["id"]
            if rid in coverage or rid in collapsed:
                continue
            rscope = rule.get("scope", default_scope)
            if scope_counts[rscope] == 0:
                continue  # already reported as empty scope above
            t = tally.get(rid)
            if t is not None and t["matched"] > 0:
                continue
            cf = rule.get("condition_field")
            if cf:
                cond_desc = (f'没有满足条件 {cf} {rule["condition_operator"]} '
                             f'{rule["condition_threshold"]} 的元素')
            else:
                cond_desc = '没有任何元素可判定'
            coverage_findings.append({
                "title": f'{rule["name"]}（未检查）',
                "description": (f'模型中有 {scope_counts[rscope]} 个'
                                f'{_SCOPE_LABEL.get(rscope, rscope)}元素，但{cond_desc}，'
                                f'规则无法判定。补充满足条件的元素后规则将自动启用。'),
                "location": "—",
                "severity": "NotChecked",
                "code_ref": rule["code_ref"],
                "type": prefix,
                "rule_id": rid,
                "floor_name": None,
            })

    coverage_findings.extend(predictive_coverage)

    # coarse MEP-vs-structure clash pre-check (bbox; refined by exact geometry later)
    clash_candidates = []
    for fl in bdata.get("floors", []):
        for c in fl.get("clashes", []):
            clash_candidates.append({**c,
                                     "floor_id": fl.get("floor_id", ""),
                                     "floor_name": fl.get("floor_name", "")})

    unit_susp = sum((fl.get("structure") or {}).get("unit_suspicious_struct", 0)
                    for fl in bdata.get("floors", []))

    all_issues = (civil_results + eee_results + building_results + structural_results
                  + mep_results + accessibility_results + predictive_results)

    # Conflict detection: same floor AND same location has both civil + eee
    loc_map = defaultdict(list)
    for iss in civil_results + eee_results:
        key = f"{iss.get('floor_id','')}::{iss.get('location','?')}"
        loc_map[key].append(iss)

    conflicts = []
    for key, issues in loc_map.items():
        types = set(i["type"] for i in issues)
        if len(types) >= 2:
            ct = [i["title"] for i in issues if i["type"] == "civil"]
            et = [i["title"] for i in issues if i["type"] == "eee"]
            floor_name = issues[0].get("floor_name", "")
            loc_name = issues[0].get("location", "?")
            t = i18n._I18N[i18n.LANG]
            conflicts.append({
                "title": t["conflict_title"].format(loc=loc_name),
                "description": t["conflict_desc"].format(floor=floor_name, loc=loc_name, n_civ=len(ct), n_eee=len(et)),
                "location": loc_name,
                "related_issues": f"{t['s_civil']}: {', '.join(ct)} | {t['s_eee']}: {', '.join(et)}",
                "type": "conflict",
                "severity": "High",
                "floor_id": issues[0].get("floor_id"),
                "floor_name": floor_name,
            })

    return {
        "civil_results": civil_results,
        "eee_results": eee_results,
        "building_results": building_results,
        "structural_results": structural_results,
        "mep_results": mep_results,
        "accessibility_results": accessibility_results,
        "coverage_findings": coverage_findings,
        "discipline_checked": checked,
        "discipline_notes": {"structural_unit_suspicious": unit_susp},
        "clash_candidates": clash_candidates,
        "conflicts": conflicts,
        "all_issues": all_issues,
        "rule_tally": tally,
        "predictive_results": predictive_results,
        "predictive_ranking": predictive_ranking,
        "predictive_monitor": predictive_monitor,
    }

def run_review_with_standard(standard_id, bdata):
    """Run the full review under a different standard without switching globals."""
    global CIVIL_RULES, EEE_RULES, BUILDING_RULES, STRUCTURAL_RULES, MEP_RULES
    global ACCESSIBILITY_RULES
    saved = (CIVIL_RULES, EEE_RULES, BUILDING_RULES, STRUCTURAL_RULES, MEP_RULES, ACCESSIBILITY_RULES)
    std = load_standard(standard_id)
    CIVIL_RULES, EEE_RULES, BUILDING_RULES = std["civil"], std["eee"], std["building"]
    STRUCTURAL_RULES = std["structural"]
    MEP_RULES = std["mep"]
    ACCESSIBILITY_RULES = std["accessibility"]
    try:
        return run_full_review(bdata)
    finally:
        CIVIL_RULES, EEE_RULES, BUILDING_RULES, STRUCTURAL_RULES, MEP_RULES, ACCESSIBILITY_RULES = saved


_SEV_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Missing": 4, "NotChecked": 5}


def aggregate_issues(issues, group_by="rule"):
    """将逐构件问题聚合为高层卡片，判定结果零改动。

    group_by: "rule" | "floor" | "system" | "room"
    返回按严重度从高到低排序的聚合卡片列表。
    """
    if not issues:
        return []

    groups = defaultdict(list)
    for iss in issues:
        if group_by == "rule":
            key = iss.get("rule_id", "unknown")
        elif group_by == "floor":
            key = iss.get("floor_name") or iss.get("floor_id") or "未命名楼层"
        elif group_by == "system":
            key = iss.get("type", "unknown")
        elif group_by == "room":
            key = iss.get("location", "未知位置")
        else:
            key = iss.get("rule_id", "unknown")
        groups[key].append(iss)

    cards = []
    for key, items in groups.items():
        top = min(items, key=lambda x: _SEV_ORDER.get(x.get("severity", "Missing"), 99))
        sev_rank = min(_SEV_ORDER.get(i.get("severity", "Missing"), 99) for i in items)
        sev_name = top.get("severity", "Missing")
        rule_id = items[0].get("rule_id", key)
        title = items[0].get("title", key)
        code_ref = items[0].get("code_ref", "")
        itype = items[0].get("type", "")

        by_floor = defaultdict(int)
        for i in items:
            fl = i.get("floor_name") or i.get("floor_id") or "—"
            by_floor[fl] += 1

        by_rule = defaultdict(int)
        for i in items:
            by_rule[i.get("rule_id", "?")] += 1

        element_count = sum(len(i.get("element_global_ids", [])) for i in items
                            if i.get("element_global_ids"))
        if element_count == 0:
            element_count = len(items)

        cards.append({
            "group_key": key,
            "group_by": group_by,
            "rule_id": rule_id,
            "title": title,
            "severity": sev_name,
            "severity_rank": sev_rank,
            "code_ref": code_ref,
            "type": itype,
            "count": len(items),
            "element_count": element_count,
            "by_floor": dict(sorted(by_floor.items())),
            "by_rule": dict(sorted(by_rule.items(), key=lambda x: -x[1])),
            "items": items,
        })

    cards.sort(key=lambda c: (c["severity_rank"], -c["count"]))
    return cards


def build_review_summary(result):
    """从审查结果生成顶部总览统计。"""
    issues = result.get("all_issues", [])
    coverage = result.get("coverage_findings", [])
    conflicts = result.get("conflicts", [])

    real_violations = [i for i in issues if i.get("severity") in
                       ("High", "Medium", "Low", "Critical")]
    missing = [i for i in issues if i.get("severity") == "Missing"]
    not_checked = [c for c in coverage if c.get("severity") == "NotChecked"]

    high = sum(1 for i in real_violations if i.get("severity") == "High")
    medium = sum(1 for i in real_violations if i.get("severity") == "Medium")
    low = sum(1 for i in real_violations if i.get("severity") == "Low")

    real_rules = set(i.get("rule_id") for i in real_violations)
    missing_rules = set(i.get("rule_id") for i in missing)
    nc_rules = set(c.get("rule_id") for c in not_checked)

    return {
        "total_issues": len(issues),
        "real_violations": len(real_violations),
        "real_rule_count": len(real_rules),
        "high_count": high,
        "medium_count": medium,
        "low_count": low,
        "missing_count": len(missing),
        "missing_rule_count": len(missing_rules),
        "missing_elements": len(missing),
        "not_checked_count": len(not_checked),
        "not_checked_rule_count": len(nc_rules),
        "conflict_count": len(conflicts),
        "disciplines": len(set(i.get("type") for i in real_violations)),
    }
