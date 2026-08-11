import json
from collections import defaultdict
from pathlib import Path
from core.config import DATA
from core.i18n import _I18N, LANG, set_language, _floor_label
from kb import steward

HERE = Path(__file__).resolve().parent.parent

CIVIL_RULES = []
EEE_RULES = []
BUILDING_RULES = []
STRUCTURAL_RULES = []
STD_META = {}

def load_standard(standard_id):
    """Load rules + meta for a given standard (cn / sg)."""
    base = DATA / "standards" / standard_id
    fallback = {"civil": [], "eee": [], "building": [], "structural": [], "meta": {}}
    result = dict(fallback)
    for key, fname in [("civil", "civil_rules.json"), ("eee", "eee_rules.json"),
                       ("building", "building_rules.json"),
                       ("structural", "structural_rules.json"), ("meta", "meta.json")]:
        p = base / fname
        if p.exists():
            try:
                result[key] = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return result

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
    global CIVIL_RULES, EEE_RULES, BUILDING_RULES, STRUCTURAL_RULES, STD_META
    std = load_standard(standard_id)
    CIVIL_RULES = std["civil"]
    EEE_RULES = std["eee"]
    BUILDING_RULES = std["building"]
    STRUCTURAL_RULES = std["structural"]
    STD_META = std["meta"]
    set_language(STD_META.get("language", "en"))
    return std

OPERATORS = {
    "<=": lambda a,b: a<=b, ">=": lambda a,b: a>=b, ">": lambda a,b: a>b,
    "<": lambda a,b: a<b, "==": lambda a,b: a==b, "!=": lambda a,b: a!=b,
    "in": lambda a,b: a in b, "not_in": lambda a,b: a not in b,
}

def run_rules(rules, item, prefix, floor_id=None, floor_name=None):
    violations = []
    for rule in rules:
        field = rule["field"]
        if field not in item:
            continue
        value = item[field]
        if value is None:
            room_name = item.get("name", item.get("id", "?"))
            violations.append({
                "title": rule["name"],
                "description": _I18N[LANG]["rule_data_missing"].format(field=field),
                "location": room_name, "severity": "Missing",
                "code_ref": rule["code_ref"], "type": prefix,
                "rule_id": rule["id"],
                "floor_id": floor_id,
                "floor_name": floor_name,
            })
            continue
        threshold = steward.resolve_threshold(rule, item)
        cond_value = None
        cond_threshold = None
        if "condition_field" in rule:
            cond_value = item.get(rule["condition_field"])
            if cond_value is None:
                continue
            cond_threshold = rule["condition_threshold"]
            if not OPERATORS[rule["condition_operator"]](cond_value, cond_threshold):
                continue
        op_func = OPERATORS[rule["operator"]]
        if op_func(value, threshold):
            continue
        room_name = item.get("name", item.get("id", "?"))
        msg = rule["message"].replace("{value}", str(value)).replace("{threshold}", str(threshold)).replace("{room_name}", str(room_name))
        if cond_value is not None:
            msg = msg.replace("{condition_value}", str(cond_value)).replace("{condition_threshold}", str(cond_threshold))
        violations.append({
            "title": rule["name"], "description": msg,
            "location": room_name, "severity": rule["severity"],
            "code_ref": rule["code_ref"], "type": prefix,
            "rule_id": rule["id"],
            "floor_id": floor_id,
            "floor_name": floor_name,
        })
    return violations

def run_full_review(bdata):
    civil_results = []
    eee_results = []
    building_results = []
    structural_results = []

    for floor in bdata.get("floors", []):
        fid = floor.get("floor_id", "")
        fname = _floor_label(floor.get("floor_name", fid))
        for room in floor.get("rooms", []):
            civil_results.extend(run_rules(CIVIL_RULES, room, "civil", fid, fname))
            eee_results.extend(run_rules(EEE_RULES, room, "eee", fid, fname))
        for zone in floor.get("fire_zones", []):
            civil_results.extend(run_rules(CIVIL_RULES, zone, "civil", fid, fname))
        for elem in floor.get("structural_elements", []):
            structural_results.extend(run_rules(STRUCTURAL_RULES, elem, "structural", fid, fname))

    bp = bdata.get("building_params", {})
    whole_label = _I18N[LANG]["whole_building"]
    building_results.extend(run_rules(BUILDING_RULES, bp, "building", None, whole_label))

    all_issues = civil_results + eee_results + building_results + structural_results

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
            t = _I18N[LANG]
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
        "conflicts": conflicts,
        "all_issues": all_issues,
    }

def run_review_with_standard(standard_id, bdata):
    """Run the full review under a different standard without switching globals."""
    global CIVIL_RULES, EEE_RULES, BUILDING_RULES, STRUCTURAL_RULES
    saved = (CIVIL_RULES, EEE_RULES, BUILDING_RULES, STRUCTURAL_RULES)
    std = load_standard(standard_id)
    CIVIL_RULES, EEE_RULES, BUILDING_RULES = std["civil"], std["eee"], std["building"]
    STRUCTURAL_RULES = std["structural"]
    try:
        return run_full_review(bdata)
    finally:
        CIVIL_RULES, EEE_RULES, BUILDING_RULES, STRUCTURAL_RULES = saved
