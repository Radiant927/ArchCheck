import ifcopenshell
from bim.extractor import parse_model
path="bim/samples/Schependomlaan.ifc"
m=ifcopenshell.open(path); st=parse_model(m,path)
shown=0
for f in st["floors"]:
    for e in f["structural_elements"]:
        if e.get("element_type")=="slab" and (e.get("thickness_m") or 9)<0.1:
            ent=m.by_guid(e["id"])
            print(e["name"][:40], "| mat:", e.get("material"), "| ObjectType:", getattr(ent,"ObjectType",None))
            shown+=1
            if shown>=8: break
    if shown>=8: break
