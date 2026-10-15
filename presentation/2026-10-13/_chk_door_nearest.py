import ifcopenshell, ifcopenshell.geom as ifcgeom
from bim.extractor import (parse_model, _length_scale, _declared_length_scale,
    _space_hull, _dist_to_poly)

path="bim/test-suites/real-project/HITOS-Large-Building_IFC2x3.ifc"
m=ifcopenshell.open(path); st=parse_model(m,path)
scale=_length_scale(m); declared=_declared_length_scale(m) or scale
bbox_scale=declared/scale
settings=ifcgeom.settings(); settings.set(settings.USE_WORLD_COORDS,True)

def storey_of_space(e):
    d=e.Decomposes
    return d[0].RelatingObject.Name if d else None
def storey_of_door(e):
    for rel in e.ContainedInStructure or []:
        return rel.RelatingStructure.Name
    return None

def centroid3(d):
    sh=ifcgeom.create_shape(settings,d); v=sh.geometry.verts
    n=len(v)//3
    return (sum(v[0::3])/n, sum(v[1::3])/n, sum(v[2::3])/n)

spaces=m.by_type("IfcSpace")
sinfo={}
for s in spaces:
    hull,_,_,isbbox=_space_hull(s,settings,bbox_scale)
    if hull:
        sinfo[s.GlobalId]=(storey_of_space(s), hull, s.Name, isbbox)

doors=m.by_type("IfcDoor")
dc={}
for d in doors:
    try: dc[d.GlobalId]=(storey_of_door(d),)+centroid3(d)
    except Exception: pass

zero={(r["id"],r["name"]) for f in st["floors"] for r in f.get("rooms",[]) if r.get("exit_count")==0}
for zid,zname in sorted(zero, key=lambda x:x[1]):
    if zid not in sinfo: continue
    ss, hull, _, isbbox = sinfo[zid]
    near=[]
    for dgid,(dstorey,x,y,z) in dc.items():
        if dstorey!=ss: continue
        dd=_dist_to_poly((x,y),hull)*scale
        if dd<1.5: near.append((round(dd,2), dgid))
    for dd,dgid in near:
        dx,dy,_ = dc[dgid][1:]
        ranks=sorted((_dist_to_poly((dx,dy),h2)*scale, nm, ib)
                     for st2,h2,nm,ib in sinfo.values() if st2==ss)
        ownrank=next((i for i,(d2,nm,ib) in enumerate(ranks) if nm==zname),None)
        print(f"room {zname:13s} bbox={isbbox} door@{dd} -> door's nearest spaces: "
              f"{[(round(d,2),nm) for d,nm,ib in ranks[:3]]}")
