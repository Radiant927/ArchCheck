# -*- coding: utf-8 -*-
"""跑提取器，打印每层 structure 计数 + 汇总，定位欠计数。"""
import sys, json
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
from bim.parser import parse_ifc

IFC = HERE / "bim/test-suites/real-project/HITOS-Large-Building_IFC2x3.ifc"
struct = parse_ifc(str(IFC), force_plan=True)

KEYS = ["walls", "slabs", "doors", "windows", "columns", "beams", "rooms"]
tot = {k: 0 for k in KEYS}
print(f"floors: {len(struct.get('floors', []))}")
for fl in struct["floors"]:
    st = fl.get("structure", {})
    print(f"\n-- {fl.get('floor_name')} @ {fl.get('elevation')}")
    for k in KEYS:
        v = st.get(k, 0)
        tot[k] += v
        print(f"     {k:9s} {v}")
print("\n== 合计 ==")
for k in KEYS:
    print(f"  {k:9s} {tot[k]}")
print("\ntop structure keys:", list(struct["floors"][0].get("structure", {}).keys()) if struct.get("floors") else None)
