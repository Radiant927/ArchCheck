import ifcopenshell
from bim.extractor import _length_scale, _door_shape_info
path="bim/test-suites/real-project/HITOS-Large-Building_IFC2x3.ifc"
m=ifcopenshell.open(path); scale=_length_scale(m)
bad=[]
for d in m.by_type("IfcDoor"):
    w,c=_door_shape_info(d,scale)
    if not c: bad.append((d.Name, w))
print("doors missing centroid:", len(bad), bad[:10])
