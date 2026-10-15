# -*- coding: utf-8 -*-
"""HITOS 板厚探针：逐块 IfcSlab 计算 PCA/bbox/Qto/extrusion，看为何多为 None。"""
import sys
from pathlib import Path
from collections import Counter
import ifcopenshell
import ifcopenshell.geom as ifcgeom

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
from bim import extractor as EX  # noqa

IFC = HERE / "bim/test-suites/real-project/HITOS-Large-Building_IFC2x3.ifc"
m = ifcopenshell.open(str(IFC))
s = ifcgeom.settings()
s.set(s.USE_WORLD_COORDS, True)

slabs = m.by_type("IfcSlab")
print("total slabs:", len(slabs))

NONSTRUCT = EX._NONSTRUCT_KEYS
buckets = Counter()
examples = {}
for e in slabs:
    mat = EX._elem_material(e)
    hay = f"{e.Name or ''} {mat or ''}".lower()
    if any(k in hay for k in NONSTRUCT):
        buckets["NONSTRUCT-filtered"] += 1
        continue
    pca = EX._pca_dims(e, s, 1.0)
    d = EX._elem_bbox_dims(e, 1.0, s)
    # Qto / extrusion raw (declared units)
    qto = EX._qto_value(e, "Qto_SlabBaseQuantities", "GrossThickness")
    ext_depth = None
    if e.Representation:
        for rep in e.Representation.Representations:
            if rep.RepresentationIdentifier == "Body":
                for it in rep.Items:
                    if it.is_a("IfcExtrudedAreaSolid") and getattr(it, "Depth", None):
                        ext_depth = it.Depth
    pca0 = pca[0] if pca else None
    bz = d[2] if d else None
    if pca0 is None:
        tag = "no-pca"
    elif pca0 <= 0.005:
        tag = f"pca<=0.005 ({pca0:.4f})"
    elif pca0 < 0.02:
        tag = f"pca 0.005-0.02 ({pca0:.4f})"
    elif pca0 < 1.0:
        tag = f"pca 0.02-1.0 OK ({pca0:.3f})"
    else:
        tag = f"pca>=1.0 ({pca0:.3f})"
    buckets[tag] += 1
    if tag not in examples:
        examples[tag] = (e.GlobalId, e.Name, mat, qto, ext_depth, pca, d)

print("\n== 结果分桶 ==")
for k, n in buckets.most_common():
    print(f"  {n:5d}  {k}")
print("\n== 样例 ==")
for k, v in examples.items():
    gid, name, mat, qto, ed, pca, d = v
    print(f"  [{k}] gid={gid} name={name!r} mat={mat!r}")
    print(f"       qto={qto} ext_depth={ed} pca={pca} bboxxyz={d}")
