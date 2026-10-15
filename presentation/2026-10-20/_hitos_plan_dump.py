# -*- coding: utf-8 -*-
"""打印每层 plan_elements/structural_elements 计数，定位 crosscheck 提取侧来源。"""
import sys
from pathlib import Path
from collections import Counter
sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
from bim.parser import parse_ifc

IFC = HERE / "bim/test-suites/real-project/HITOS-Large-Building_IFC2x3.ifc"
struct = parse_ifc(str(IFC), force_plan=True)

pk = Counter()
sk = Counter()
for fl in struct["floors"]:
    for pe in fl.get("plan_elements", []):
        pk[pe.get("kind")] += 1
    for se in fl.get("structural_elements", []):
        sk[se.get("element_type")] += 1
print("plan_elements by kind:", dict(pk))
print("structural_elements by type:", dict(sk))
print("floors:", len(struct["floors"]))
# structure 汇总
tot = Counter()
for fl in struct["floors"]:
    for k, v in fl.get("structure", {}).items():
        if isinstance(v, int):
            tot[k] += v
print("structure totals:", {k: tot[k] for k in
      ["walls", "slabs", "doors", "windows", "columns", "beams"]})
