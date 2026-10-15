"""诊断脚本：逐模型、逐规则导出被标记问题的构件名分布（不改动引擎/提取器）。

输出 presentation/2026-10-05/_diag_issue_elements.json
"""
import sys, json, io
from collections import defaultdict, Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from bim.parser import parse_ifc, build_review_data
from core import engine

MODELS = [
    ("FZK_Haus", "bim/samples/FZK_Haus.ifc"),
    ("office_3f", "bim/samples/office_3f.ifc"),
    ("Duplex_MEP", "bim/samples/Duplex_MEP_20110907.ifc"),
    ("Schependomlaan", "bim/samples/Schependomlaan.ifc"),
    ("HITOS", "bim/test-suites/real-project/HITOS-Large-Building_IFC2x3.ifc"),
    ("Smiley-West", "bim/test-suites/real-project/Smiley-West-Office_Archicad20_IFC2x3.ifc"),
]


def norm_name(nm):
    """Collapse trailing instance numbers so element families can be counted."""
    s = str(nm or "?")
    # strip trailing digits / separators
    return s


def run_model(name, rel):
    path = ROOT / rel
    struct = parse_ifc(path)
    bdata = build_review_data(struct)
    engine.set_standard("cn")
    res = engine.run_full_review(bdata)
    issues = res.get("all_issues", [])
    by_rule = defaultdict(list)
    for iss in issues:
        by_rule[(iss.get("rule_id"), iss.get("title"), iss.get("severity"),
                 iss.get("type"))].append(iss)
    rules_out = []
    for (rid, title, sev, typ), items in sorted(by_rule.items(), key=lambda x: -len(x[1])):
        names = Counter(norm_name(i.get("location")) for i in items)
        floors = Counter(str(i.get("floor_name")) for i in items)
        rules_out.append({
            "rule_id": rid, "title": title, "severity": sev, "type": typ,
            "count": len(items),
            "top_locations": names.most_common(12),
            "unique_location_count": len(names),
            "floors": floors.most_common(),
        })
    qa = struct.get("qa", {})
    return {
        "model": name, "path": rel,
        "qa_score": qa.get("score"), "qa_fatal": qa.get("fatal"),
        "total_issues": len(issues),
        "rule_count": len(by_rule),
        "rules": rules_out,
    }


def main():
    out = []
    for name, rel in MODELS:
        print(f"=== {name} ===", flush=True)
        try:
            out.append(run_model(name, rel))
        except Exception as e:
            import traceback; traceback.print_exc()
            out.append({"model": name, "error": str(e)})
    dest = Path(__file__).resolve().parent / "_diag_issue_elements.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("WROTE", dest)


if __name__ == "__main__":
    main()
