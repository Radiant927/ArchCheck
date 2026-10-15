import ifcopenshell, ifcopenshell.geom as ifcgeom
from bim.extractor import (parse_model, _length_scale, _declared_length_scale,
    _space_hull, _dist_to_poly)

path="bim/test-suites/real-project/HITOS-Large-Building_IFC2x3.ifc"
m=ifcopenshell.open(path); st=parse_model(m,path)
scale=_length_scale(m); declared=_declared_length_scale(m) or scale
bbox_scale=declared/scale
settings=ifcgeom.settings(); settings.set(settings.USE_WORLD_COORDS,True)

def elev_m(s): return (s.Elevation or 0)*0.001
storeys=sorted(m.by_type("IfcBuildingStorey"), key=lambda s:s.Elevation or 0)
selev={s.Name: elev_m(s) for s in storeys}

def storey_of(e):
    if e.is_a("IfcSpace"):
        d=e.Decomposes
        if d: return d[0].RelatingObject.Name
        return None
    for rel in e.ContainedInStructure or []:
        return rel.RelatingStructure.Name
    return None

def dcentroid(d):
    sh=ifcgeom.create_shape(settings,d); v=sh.geometry.verts
    n=len(v)//3
    return (sum(v[0::3])/n, sum(v[1::3])/n, sum(v[2::3])/n)

id2sp={s.GlobalId:s for s in m.by_type("IfcSpace")}
doors=m.by_type("IfcDoor")
dc={}
for d in doors:
    try: dc[d.GlobalId]=dcentroid(d)
    except Exception: pass

zero=[r for f in st["floors"] for r in f.get("rooms",[]) if r.get("exit_count")==0]
for r in zero:
    sp=id2sp.get(r["id"])
    hull,_,_,_=_space_hull(sp,settings,bbox_scale)
    ss=storey_of(sp); rz=selev.get(ss)
    cands=[]
    for d in doors:
        c=dc.get(d.GlobalId)
        if not c or not hull: continue
        dd=_dist_to_poly((c[0],c[1]),hull)*scale
        if dd<2.0:
            dz=(c[2]*scale-rz) if rz is not None else None
            cands.append((round(dd,2), round(dz,2) if dz is not None else None,
                          storey_of(d), d.Name))
    cands.sort(key=lambda x:(x[0], abs(x[1] or 9)))
    print(f'ROOM {r["name"]:13s} {ss:14s} z={rz} :: {cands[:3]}')
