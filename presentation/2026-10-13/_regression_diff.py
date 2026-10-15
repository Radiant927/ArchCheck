import sys, json
from pathlib import Path
from collections import Counter
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
TARGET={"BLD-001","BLD-002","BLD-003","BLD-004","BLD-007","BLD-008","BLD-009",
        "STR-001","STR-002","STR-003","STR-004","CIVIL-006","MEP-013"}

base={r["model"]:r for r in json.load(open(Path(__file__).with_name("_diag_issue_elements.json"),encoding="utf-8"))}
bad=0
for name,rel in MODELS:
    struct=parse_ifc(ROOT/rel); bdata=build_review_data(struct)
    engine.set_standard("cn"); res=engine.run_full_review(bdata)
    cur=Counter((i["rule_id"],i["severity"]) for i in res.get("all_issues",[]))
    old=Counter()
    for rr in base[name]["rules"]:
        old[(rr["rule_id"],rr["severity"])]=rr["count"]
    keys=set(cur)|set(old)
    total_cur=sum(v for (r,s),v in cur.items())
    print(f"== {name}: total {base[name]['total_issues']} -> {total_cur}")
    for k in sorted(keys):
        if cur[k]!=old[k]:
            tag="TARGET" if k[0] in TARGET else "!! NON-TARGET !!"
            if k[0] not in TARGET: bad+=1
            print(f"   {tag:18s} {k} {old[k]} -> {cur[k]}")
print("NON-TARGET REGRESSIONS:",bad)
