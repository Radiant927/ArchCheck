import sys, json
from pathlib import Path
from collections import Counter, defaultdict
sys.stdout.reconfigure(encoding="utf-8")
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT))
from bim.parser import parse_ifc, build_review_data
from core import engine

MODELS=[
 ("FZK_Haus","bim/samples/FZK_Haus.ifc"),
 ("office_3f","bim/samples/office_3f.ifc"),
 ("Duplex_MEP","bim/samples/Duplex_MEP_20110907.ifc"),
 ("Schependomlaan","bim/samples/Schependomlaan.ifc"),
 ("HITOS","bim/test-suites/real-project/HITOS-Large-Building_IFC2x3.ifc"),
 ("Smiley-West","bim/test-suites/real-project/Smiley-West-Office_Archicad20_IFC2x3.ifc"),
]
out=[]
for name,rel in MODELS:
    struct=parse_ifc(ROOT/rel); bdata=build_review_data(struct)
    engine.set_standard("cn"); res=engine.run_full_review(bdata)
    summ=engine.build_review_summary(res)
    issues=res.get("all_issues",[])
    rules=defaultdict(int)
    for i in issues: rules[(i["rule_id"],i["severity"])]+=1
    out.append({
        "model":name,"path":rel,
        "total":len(issues),
        "distinct_rules":len({i["rule_id"] for i in issues}),
        "missing":summ["missing_count"],
        "not_checked":summ["not_checked_count"],
        "real_violations":len(issues)-summ["missing_count"],
        "rules":[{"rule_id":r,"severity":s,"count":c} for (r,s),c in sorted(rules.items())],
    })
Path(__file__).with_name("_postfix_data.json").write_text(
    json.dumps(out,ensure_ascii=False,indent=1),encoding="utf-8")
for o in out:
    print(o["model"], o["total"], "rules",o["distinct_rules"],
          "missing",o["missing"],"notchecked",o["not_checked"])
