# -*- coding: utf-8 -*-
"""HITOS 欠计数根因探针：真值/含于楼层/几何成功 三档对比。"""
import sys
from pathlib import Path
import ifcopenshell
import ifcopenshell.geom as ifcgeom

sys.stdout.reconfigure(encoding="utf-8")
IFC = Path(r"C:\Users\32800\Desktop\NTU pre\ArchCheck\bim\test-suites\real-project\HITOS-Large-Building_IFC2x3.ifc")
m = ifcopenshell.open(str(IFC))

# storey 内含
contained = set()
for rel in m.by_type("IfcRelContainedInSpatialStructure"):
    rel_def = rel.RelatingStructure
    if rel_def is not None and rel_def.is_a("IfcBuildingStorey"):
        for e in rel.RelatedElements:
            contained.add(e.GlobalId)

s = ifcgeom.settings()
s.set(s.USE_WORLD_COORDS, True)

TY = ["IfcWall", "IfcSlab", "IfcDoor", "IfcWindow", "IfcColumn", "IfcBeam"]
print(f"{'type':10s} {'total':>6s} {'contained':>10s} {'geomOK':>8s} {'bboxOK':>8s}")
for t in TY:
    els = m.by_type(t)
    ncon = sum(1 for e in els if e.GlobalId in contained)
    ok = 0
    bboxok = 0
    for e in els:
        try:
            sh = ifcgeom.create_shape(s, e)
            v = sh.geometry.verts
            if len(v) >= 6:
                ok += 1
                xs = v[0::3]; ys = v[1::3]; zs = v[2::3]
                b = (min(xs), min(ys), max(xs), max(ys), min(zs), max(zs))
                if all(abs(x) < 1e6 for x in b):
                    bboxok += 1
        except Exception:
            pass
    print(f"{t:10s} {len(els):>6d} {ncon:>10d} {ok:>8d} {bboxok:>8d}")

# 全局
print("\n总 IfcBuildingStorey:", len(m.by_type("IfcBuildingStorey")))
print("总 IfcSpace:", len(m.by_type("IfcSpace")))
print("schema:", m.schema)
