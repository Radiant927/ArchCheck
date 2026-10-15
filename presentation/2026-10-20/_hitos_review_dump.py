# -*- coding: utf-8 -*-
"""跑 HITOS 完整审查，导出 all_issues + 聚合卡片，供金标准抽样/裁定。"""
import sys, json
from pathlib import Path
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))

from bim.parser import parse_ifc
from bim.extractor import build_review_data
from core import engine

IFC = HERE / "bim/test-suites/real-project/HITOS-Large-Building_IFC2x3.ifc"
OUT = Path(__file__).resolve().parent / "_hitos_review"
OUT.mkdir(exist_ok=True)

print("parsing…")
struct = parse_ifc(str(IFC), force_plan=True)
bdata = build_review_data(struct)
engine.set_standard("cn")
print("reviewing…")
res = engine.run_full_review(bdata)

issues = res.get("all_issues", [])
agg = engine.aggregate_issues(issues, group_by="rule")
print(f"all_issues: {len(issues)}  aggregated cards: {len(agg)}")
print("severity:", dict(Counter(i.get("severity") for i in issues)))
print("type:", dict(Counter(i.get("type") for i in issues)))

(OUT / "all_issues.json").write_text(
    json.dumps(issues, ensure_ascii=False, indent=1), encoding="utf-8")
(OUT / "aggregated.json").write_text(
    json.dumps(agg, ensure_ascii=False, indent=1), encoding="utf-8")
print("wrote", OUT / "all_issues.json", "and aggregated.json")

# 顶部卡片摘要
print("\n== 聚合卡片（Top 20 by 数量）==")
for c in sorted(agg, key=lambda x: -len(x.get("issues", x.get("items", []))))[:20]:
    items = c.get("issues", c.get("items", []))
    print(f"  [{c.get('severity','?'):8s}] {c.get('rule_id','?'):10s} "
          f"n={len(items):4d}  {c.get('title','')[:50]}")
