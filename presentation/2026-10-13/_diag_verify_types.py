"""核验疑似误报构件在原始 IFC 中的真实类型/预定义类型/材料。"""
import sys
from pathlib import Path
import ifcopenshell
from collections import defaultdict, Counter

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]


def pd(e):
    for a in ("PredefinedType", "ObjectType"):
        v = getattr(e, a, None)
        if v not in (None, "", "NOTDEFINED", "USERDEFINED"):
            return f"{a}={v}"
    return "?"


def mat(e):
    try:
        for rel in getattr(e, "HasAssociations", []) or []:
            if rel.is_a("IfcRelAssociatesMaterial"):
                m = rel.RelatingMaterial
                if m.is_a("IfcMaterial"):
                    return m.Name
                if m.is_a("IfcMaterialLayerSetUsage"):
                    return m.ForLayerSet.LayerSetName
                if m.is_a("IfcMaterialLayerSet"):
                    return m.LayerSetName
    except Exception:
        pass
    return "?"


def thickness(e):
    try:
        for rel in getattr(e, "IsDefinedBy", []) or []:
            if rel.is_a("IfcRelDefinesByProperties"):
                p = rel.RelatingPropertyDefinition
                if p.is_a("IfcElementQuantity"):
                    for q in p.Quantities or []:
                        if "Thickness" in (q.Name or ""):
                            return f"{q.Name}={getattr(q,'LengthValue',None)}"
    except Exception:
        pass
    return ""


def scan(rel, type_names, name_filter=None):
    m = ifcopenshell.open(str(ROOT / rel))
    print(f"\n##### {rel}")
    for tn in type_names:
        agg = Counter()
        for e in m.by_type(tn):
            nm = getattr(e, "Name", "") or ""
            if name_filter and not any(f.lower() in nm.lower() for f in name_filter):
                continue
            key = (e.is_a(), pd(e), mat(e), thickness(e))
            agg[key] += 1
        if agg:
            print(f"  -- {tn} --")
            for k, c in agg.most_common(20):
                print(f"     x{c:<4} {k}")


if __name__ == "__main__":
    # HITOS: suspended ceilings named *himling
    scan("bim/test-suites/real-project/HITOS-Large-Building_IFC2x3.ifc",
         ["IfcSlab", "IfcCovering"], name_filter=["himling"])
    # HITOS real slabs
    scan("bim/test-suites/real-project/HITOS-Large-Building_IFC2x3.ifc",
         ["IfcSlab"], name_filter=["Dekke"])
    # Schependomlaan: screed/floor/ceiling flagged as slab
    scan("bim/samples/Schependomlaan.ifc",
         ["IfcSlab", "IfcCovering"],
         name_filter=["dekvloer", "vloerveld", "dakvloer", "plafond"])
    # Schependomlaan flagged "columns" / "beams"
    scan("bim/samples/Schependomlaan.ifc",
         ["IfcColumn", "IfcBeam", "IfcMember"],
         name_filter=["baluster", "K80/80", "staallatei", "fund", "HEA180", "HEB220", "hoeklijn"])
