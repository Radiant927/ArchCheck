from collections import Counter
import ifcopenshell
from bim.extractor import parse_model

models = {
 "FZK":"bim/samples/FZK_Haus.ifc",
 "office":"bim/samples/office_3f.ifc",
 "Duplex":"bim/samples/Duplex_MEP_20110907.ifc",
 "Schepen":"bim/samples/Schependomlaan.ifc",
 "HITOS":"bim/test-suites/real-project/HITOS-Large-Building_IFC2x3.ifc",
 "Smiley":"bim/test-suites/real-project/Smiley-West-Office_Archicad20_IFC2x3.ifc",
}
for tag, path in models.items():
    m = ifcopenshell.open(path)
    st = parse_model(m, path)
    slabs = []
    for f in st.get("floors", []):
        slabs.extend(e for e in f.get("structural_elements", []) if e.get("element_type") == "slab")
    thin = [s for s in slabs if (s.get("thickness_m") or 9) < 0.1]
    print(f"== {tag}: slabs={len(slabs)} thin(<.1)={len(thin)}")
    c = Counter((s.get("material_class"), s.get("cast_in_place"), round(s.get("thickness_m") or -1,3)) for s in thin)
    for k,v in c.most_common(12):
        print("   thin", k, v)
