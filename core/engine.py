import json
from collections import defaultdict
from pathlib import Path
from core.config import DATA
from core import i18n
from core.i18n import set_language, _floor_label
from kb import steward

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
    if not cf:
        return True
    cv = item.get(cf)
    if cv is None:
        return False  # filter field absent -> cannot confirm applicability -> skip (avoid noise)
    return bool(OPERATORS[rule["condition_operator"]](cv, rule["condition_threshold"]))


def run_rules(rules, item, prefix, scope, floor_id=None, floor_name=None, coverage=None):
    """Run a rule set against one item.

    ``scope`` is the element type being judged (room / zone / equipment / structure /
    pipe / duct / building). A rule may declare its own ``scope``; rules whose scope
    does not match are skipped entirely so they never report a spurious missing-field
    gap on the wrong element type.

    When a rule applies to the item but the judged field is absent from the model,
    it is recorded into ``coverage`` (rule_id -> stats) instead of silently skipped —
    this is what turns "dead rules" into an honest "未检查（缺字段）" report.
    """
    violations = []
    default_scope = _DEFAULT_SCOPE.get(prefix, "room")
    for rule in rules:
        if rule.get("scope", default_scope) != scope:
            continue
        field = rule["field"]
        if field not in item:
            if _rule_applies(rule, item):
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
        cond_value = None
        cond_threshold = None
        if "condition_field" in rule:
            cond_value = item.get(rule["condition_field"])
            if cond_value is None:
                continue
            cond_threshold = rule["condition_threshold"]
            if not OPERATORS[rule["condition_operator"]](cond_value, cond_threshold):
                continue
        value = item[field]
        if value is None:
            room_name = item.get("name", item.get("id", "?"))
            violations.append({
                "title": rule["name"],
                "description": i18n._I18N[i18n.LANG]["rule_data_missing"].format(field=field),
                "location": room_name, "severity": "Missing",
                "code_ref": rule["code_ref"], "type": prefix,
                "rule_id": rule["id"],
                "floor_id": floor_id,
                "floor_name": floor_name,
            })
            continue
        threshold = steward.resolve_threshold(rule, item)
        op_func = OPERATORS[rule["operator"]]
        if op_func(value, threshold):
            continue
        room_name = item.get("name", item.get("id", "?"))
        msg = rule["message"].replace("{value}", str(value)).replace("{threshold}", str(threshold)).replace("{room_name}", str(room_name))
        if cond_value is not None:
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
        })
    return violations

_SCOPE_LABEL = {"room": "房间", "zone": "防火分区", "equipment": "电气设备",
                "structure": "结构构件", "pipe": "管道", "duct": "风管", "building": "全楼"}


def run_full_review(bdata):
    civil_results = []
    eee_results = []
    building_results = []
    structural_results = []
    mep_results = []
    accessibility_results = []
    coverage = {}
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
            civil_results.extend(run_rules(CIVIL_RULES, room, "civil", "room", fid, fname, coverage))
            accessibility_results.extend(run_rules(ACCESSIBILITY_RULES, room, "accessibility", "room", fid, fname, coverage))
        eqs = floor.get("electrical_elements", [])
        checked["eee"] += len(eqs)
        scope_counts["equipment"] += len(eqs)
        for eq in eqs:
            eee_results.extend(run_rules(EEE_RULES, eq, "eee", "equipment", fid, fname, coverage))
        zones = floor.get("fire_zones", [])
        scope_counts["zone"] += len(zones)
        for zone in zones:
            checked["civil"] += 1
            civil_results.extend(run_rules(CIVIL_RULES, zone, "civil", "zone", fid, fname, coverage))
        elems = floor.get("structural_elements", [])
        checked["structural"] += len(elems)
        scope_counts["structure"] += len(elems)
        for elem in elems:
            structural_results.extend(run_rules(STRUCTURAL_RULES, elem, "structural", "structure", fid, fname, coverage))
        pipes = floor.get("pipes", [])
        ducts = floor.get("ducts", [])
        checked["mep"] += sum(1 for p in pipes if p.get("pipe_type") not in ("unknown",)) + len(ducts)
        scope_counts["pipe"] += len(pipes)
        scope_counts["duct"] += len(ducts)
        for pipe in pipes:
            mep_results.extend(run_rules(MEP_RULES, pipe, "mep", "pipe", fid, fname, coverage))
        for duct in ducts:
            mep_results.extend(run_rules(MEP_RULES, duct, "mep", "duct", fid, fname, coverage))

    bp = bdata.get("building_params", {})
    whole_label = i18n._I18N[i18n.LANG]["whole_building"]
    checked["building"] = 1
    scope_counts["building"] += 1
    building_results.extend(run_rules(BUILDING_RULES, bp, "building", "building", None, whole_label, coverage))
    accessibility_results.extend(run_rules(ACCESSIBILITY_RULES, bp, "accessibility", "building", None, whole_label, coverage))

    # coverage report — rules that exist but could not judge because the model
    # lacks their field (per-rule aggregation) or their element scope entirely.
    coverage_findings = []
    empty_scope_rules = defaultdict(list)
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

    # coarse MEP-vs-structure clash pre-check (bbox; refined by exact geometry later)
    clash_candidates = []
    for fl in bdata.get("floors", []):
        for c in fl.get("clashes", []):
            clash_candidates.append({**c,
                                     "floor_id": fl.get("floor_id", ""),
                                     "floor_name": fl.get("floor_name", "")})

    unit_susp = sum((fl.get("structure") or {}).get("unit_suspicious_struct", 0)
                    for fl in bdata.get("floors", []))

    all_issues = civil_results + eee_results + building_results + structural_results + mep_results

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
