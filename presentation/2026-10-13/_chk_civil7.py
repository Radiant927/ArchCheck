from collections import Counter
import ifcopenshell, ifcopenshell.geom as ifcgeom
from bim.extractor import (parse_model, _length_scale, _declared_length_scale,
    _space_hull, _door_shape_info, _dist_to_poly)

path = "bim/test-suites/real-project/HITOS-Large-Building_IFC2x3.ifc"
m = ifcopenshell.open(path)
st = parse_model(m, path)
scale = _length_scale(m)
declared = _declared_length_scale(m) or scale
bbox_scale = declared / scale
settings = ifcgeom.settings(); settings.set(settings.USE_WORLD_COORDS, True)

zero = []
for f in st.get("floors", []):
    for r in f.get("rooms", []):
        if r.get("exit_count") == 0:
            zero.append((f.get("name"), r.get("name"), r.get("id"), r.get("type")))
print("zero-exit rooms:", len(zero))
print("types:", Counter(t for *_, t in zero).most_common())

id2space = {s.GlobalId: s for s in m.by_type("IfcSpace")}
doors = m.by_type("IfcDoor")
print("total doors:", len(doors))
dgeom = {d.GlobalId: _door_shape_info(d, scale) for d in doors}

def storey_of(e):
    if e.is_a("IfcSpace"):
        d = e.Decomposes
        if d:
            rs = d[0].RelatingObject
            return rs.Name or rs.GlobalId
        return None
    for rel in e.ContainedInStructure or []:
        return rel.RelatingStructure.Name or rel.RelatingStructure.GlobalId
    return None

buckets = Counter()
rows = []
for fname, rname, rid, rtype in zero:
    sp = id2space.get(rid)
    if sp is None:
        buckets["space_entity_missing"] += 1; continue
    bounds = sp.BoundedBy or []
    door_bounds = [b for b in bounds if b.RelatedBuildingElement and b.RelatingBuildingElement.is_a("IfcDoor")] if False else \
                  [b for b in bounds if b.RelatedBuildingElement and b.RelatedBuildingElement.is_a("IfcDoor")]
    hull, centroid, au, isbbox = _space_hull(sp, settings, bbox_scale)
    sstorey = storey_of(sp)
    best_any = best_same = None
    for d in doors:
        w, c = dgeom[d.GlobalId]
        if not c or not hull: continue
        dd = _dist_to_poly(c, hull) * scale
        if best_any is None or dd < best_any[0]:
            best_any = (dd, d.Name)
        if storey_of(d) == sstorey and (best_same is None or dd < best_same[0]):
            best_same = (dd, d.Name)
    if door_bounds: buckets["has_door_boundary"] += 1
    elif not hull: buckets["no_hull"] += 1
    elif best_same and best_same[0] <= 0.5: buckets["door_within_.5_same_storey(!ASSOC MISS)"] += 1
    elif best_any and best_any[0] <= 0.5: buckets["door_within_.5_other_storey"] += 1
    elif best_same and best_same[0] <= 1.5: buckets["nearest_same_0.5-1.5"] += 1
    else: buckets["isolated(no door near)"] += 1
    rows.append((rname, rtype, len(bounds), bool(door_bounds),
                 round(best_any[0],2) if best_any else None,
                 round(best_same[0],2) if best_same else None))

print("buckets:", dict(buckets))
for r in rows[:60]:
    print(r)
