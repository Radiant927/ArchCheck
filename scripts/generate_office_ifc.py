"""Generate a clean multi-storey office IFC sample for ArchCheck.

Deterministic 3-storey office building (38m x 8.5m footprint), full of the
physical detail an IFC viewer should show:
- spaces with function-typed names (Corridor / Office / Meeting Room / Stairwell)
  + box geometry, wired to storeys via IfcRelAggregates
- perimeter walls, partition walls, corridor spine wall with door openings
- one floor slab per storey + roof slab; ground slab is floor-1's slab
- structural grid: IfcColumn + IfcBeam along the two structural lines
- IfcWindow on the south facade, one per room
- one IfcDoor per room (Pset_DoorCommon.OverallWidth=0.9) + IfcRelSpaceBoundary
- IfcStair treads in the two stairwells
All solid geometry is IfcFacetedBrep boxes (this ifcopenshell build cannot
process swept solids).

Output: bim/samples/office_3f.ifc
"""
import ifcopenshell
import ifcopenshell.guid
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "bim" / "samples" / "office_3f.ifc"

# Building geometry (metres)
FOOT_W, FOOT_D = 38.0, 8.5
STOREY_H = 3.6
WALL_H = 3.3
DOOR_W, DOOR_H = 0.9, 2.1

# Per-storey layout: (name, type, x, y, w, d); corridor runs along y=0..2.5
def floor_rooms(floor_no):
    n = floor_no * 100
    return [
        ("Corridor", "Corridor", 0.0, 0.0, 38.0, 2.5),
        (f"Stairwell {floor_no}A", "Stairwell", 0.0, 2.5, 4.0, 6.0),
        (f"Office {n + 1}", "Office", 4.0, 2.5, 6.0, 6.0),
        (f"Office {n + 2}", "Office", 10.0, 2.5, 6.0, 6.0),
        (f"Office {n + 3}", "Office", 16.0, 2.5, 6.0, 6.0),
        (f"Office {n + 4}", "Office", 22.0, 2.5, 6.0, 6.0),
        (f"Meeting Room {n + 5}", "Meeting Room", 28.0, 2.5, 6.0, 6.0),
        (f"Stairwell {floor_no}B", "Stairwell", 34.0, 2.5, 4.0, 6.0),
    ]


def _pt(model, x, y, z):
    return model.create_entity("IfcCartesianPoint", [float(x), float(y), float(z)])


def _placement(model, parent, x, y, z):
    return model.create_entity(
        "IfcLocalPlacement", PlacementRelTo=parent,
        RelativePlacement=model.create_entity("IfcAxis2Placement3D", Location=_pt(model, x, y, z)))


def _brep(model, w, d, h, ox=0.0, oy=0.0, oz=0.0):
    """A single IfcFacetedBrep box, offset by (ox, oy, oz)."""
    P = [(ox, oy, oz), (ox + w, oy, oz), (ox + w, oy + d, oz), (ox, oy + d, oz),
         (ox, oy, oz + h), (ox + w, oy, oz + h), (ox + w, oy + d, oz + h), (ox, oy + d, oz + h)]
    pts = [_pt(model, x, y, z) for x, y, z in P]
    faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
             (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    bounds = [model.create_entity("IfcFaceOuterBound",
                                  Bound=model.create_entity("IfcPolyLoop",
                                                            Polygon=[pts[i] for i in f]),
                                  Orientation=True) for f in faces]
    brep = model.create_entity("IfcFacetedBrep", Outer=model.create_entity(
        "IfcClosedShell", CfsFaces=[model.create_entity("IfcFace", Bounds=[b]) for b in bounds]))
    return brep


def _box_rep(model, context3d, boxes):
    """A body representation from a list of (ox, oy, oz, w, d, h) boxes."""
    items = [_brep(model, w, d, h, ox, oy, oz) for (ox, oy, oz, w, d, h) in boxes]
    rep = model.create_entity("IfcShapeRepresentation", ContextOfItems=context3d,
                              RepresentationIdentifier="Body", RepresentationType="Brep",
                              Items=items)
    return model.create_entity("IfcProductDefinitionShape", Representations=[rep])


def _box_rep_pts(model, context3d, pts):
    """A body representation from one explicit 8-vertex box (e.g. sloped pipe)."""
    pts = [_pt(model, x, y, z) for x, y, z in pts]
    faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
             (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    bounds = [model.create_entity("IfcFaceOuterBound",
                                  Bound=model.create_entity("IfcPolyLoop",
                                                            Polygon=[pts[i] for i in f]),
                                  Orientation=True) for f in faces]
    brep = model.create_entity("IfcFacetedBrep", Outer=model.create_entity(
        "IfcClosedShell", CfsFaces=[model.create_entity("IfcFace", Bounds=[b]) for b in bounds]))
    rep = model.create_entity("IfcShapeRepresentation", ContextOfItems=context3d,
                              RepresentationIdentifier="Body", RepresentationType="Brep",
                              Items=[brep])
    return model.create_entity("IfcProductDefinitionShape", Representations=[rep])


def _faceted_box_rep(model, context3d, w, d, h):
    return _box_rep(model, context3d, [(0.0, 0.0, 0.0, w, d, h)])


def _element(model, context3d, parent, etype, name, x, y, z, boxes):
    """Create a physical element of ``etype`` with a brep box representation."""
    return model.create_entity(etype, GlobalId=ifcopenshell.guid.new(), Name=name,
                               ObjectPlacement=_placement(model, parent, x, y, z),
                               Representation=_box_rep(model, context3d, boxes))


def _box_space(model, context3d, placement, name, w, d, h=3.0):
    return model.create_entity("IfcSpace", GlobalId=ifcopenshell.guid.new(), Name=name,
                               ObjectType="Space", CompositionType="ELEMENT",
                               ObjectPlacement=placement,
                               Representation=_faceted_box_rep(model, context3d, w, d, h))


def _pset(model, entity, name, props):
    values = []
    for key, (ptype, val) in props.items():
        nominal = model.create_entity(ptype, val)
        values.append(model.create_entity("IfcPropertySingleValue", Name=key, NominalValue=nominal))
    ps = model.create_entity("IfcPropertySet", GlobalId=ifcopenshell.guid.new(),
                             Name=name, HasProperties=values)
    model.create_entity("IfcRelDefinesByProperties", GlobalId=ifcopenshell.guid.new(),
                        RelatingPropertyDefinition=ps, RelatedObjects=[entity])


def _door(model, context3d, placement, width=DOOR_W, height=DOOR_H):
    door = model.create_entity("IfcDoor", GlobalId=ifcopenshell.guid.new(),
                               Name=f"Door {width}m", ObjectPlacement=placement,
                               OverallWidth=width, OverallHeight=height,
                               Representation=_faceted_box_rep(model, context3d, width, 0.2, height))
    _pset(model, door, "Pset_DoorCommon", {"OverallWidth": ("IfcReal", width),
                                           "OverallHeight": ("IfcReal", height)})
    return door


def _spine_segments(door_centers, x0=0.0, x1=FOOT_W, opening=DOOR_W):
    """Wall segments along y=2.5 with 0.9m openings at each door centre."""
    cuts = sorted((dc - opening / 2, dc + opening / 2) for dc in door_centers)
    segs, cur = [], x0
    for a, b in cuts:
        if a > cur:
            segs.append((cur, a))
        cur = max(cur, b)
    if cur < x1:
        segs.append((cur, x1))
    return segs


def _pipe(model, context3d, parent, name, x, y, z, length, diameter, pipe_type,
          slope=None, along="x", slope_geom=None):
    """An IfcFlowSegment pipe with ArchCheckPipeParams.

    slope_geom != None  → build a sloped prism (rise = slope_geom*length) and,
    when slope is None, leave it to the parser's geometry fallback — this tests
    the real-model path where the slope lives only in the geometry.
    """
    if slope_geom:
        rise = slope_geom * length
        if along == "x":
            pts = [(0, 0, 0), (length, 0, rise), (length, diameter, rise), (0, diameter, 0),
                   (0, 0, diameter), (length, 0, rise + diameter),
                   (length, diameter, rise + diameter), (0, diameter, diameter)]
        else:
            pts = [(0, 0, 0), (0, length, rise), (diameter, length, rise), (diameter, 0, 0),
                   (0, 0, diameter), (0, length, rise + diameter),
                   (diameter, length, rise + diameter), (diameter, 0, diameter)]
        pipe = model.create_entity("IfcFlowSegment", GlobalId=ifcopenshell.guid.new(), Name=name,
                                   ObjectPlacement=_placement(model, parent, x, y, z),
                                   Representation=_box_rep_pts(model, context3d, pts))
    else:
        boxes = [(0, 0, 0, length, diameter, diameter)] if along == "x" \
            else [(0, 0, 0, diameter, length, diameter)]
        pipe = _element(model, context3d, parent, "IfcFlowSegment", name, x, y, z, boxes)
    props = {"pipe_type": ("IfcLabel", pipe_type), "diameter_m": ("IfcReal", diameter)}
    if slope is not None:
        props["slope"] = ("IfcReal", slope)
    _pset(model, pipe, "ArchCheckPipeParams", props)
    return pipe


def _room_eee_params(rtype):
    """Real per-room electrical summary declared in the model (ArchCheckEEEParams).

    Kept consistent with the per-room electrical equipment elements (the room
    Pset is the summary, the equipment are the judged objects).
    """
    if rtype == "Corridor":
        return {"has_emergency_light": ("IfcBoolean", False),
                "dist_to_water_m": ("IfcReal", 4.0),
                "circuit_load_a": ("IfcReal", 8.0),
                "outlet_spacing_m": ("IfcReal", 5.0)}
    if rtype == "Stairwell":
        return {"has_emergency_light": ("IfcBoolean", True),
                "dist_to_water_m": ("IfcReal", 5.0),
                "circuit_load_a": ("IfcReal", 6.0),
                "outlet_spacing_m": ("IfcReal", 5.0)}
    return {"has_emergency_light": ("IfcBoolean", True),
            "dist_to_water_m": ("IfcReal", 3.0),
            "circuit_load_a": ("IfcReal", 12.0),
            "outlet_spacing_m": ("IfcReal", 3.0)}


def _equipment(model, context3d, parent, name, etype, x, y, z, w, d, h, equip_type, room_ref="", **eee):
    """An electrical equipment element (distribution board / light / socket) with
    its real electrical params in ArchCheckEEEEquip, tagged with the room it serves."""
    eq = _element(model, context3d, parent, etype, name, x, y, z, [(0, 0, 0, w, d, h)])
    props = {"equipment_type": ("IfcLabel", equip_type), "room_ref": ("IfcLabel", room_ref)}
    for k, v in eee.items():
        props[k] = ("IfcBoolean", v) if isinstance(v, bool) else ("IfcReal", float(v))
    _pset(model, eq, "ArchCheckEEEEquip", props)
    return eq


def _room_equipment(model, context3d, parent, name, rtype, cx, cy):
    """A lighting fixture + a socket per room (real electrical elements the EEE
    rules judge). Corridors have a non-emergency luminaire -> EEE-001 finding."""
    emerg = rtype != "Corridor"
    power = 36.0 if rtype in ("Office", "Meeting Room") else 18.0
    spacing = 3.0 if rtype in ("Office", "Meeting Room") else 5.0
    return [
        _equipment(model, context3d, parent, f"Light {name}", "IfcLightFixture",
                   cx - 0.5, cy, 2.6, 0.5, 0.1, 0.1, "lighting",
                   room_ref=name, has_emergency=emerg, power_w=power),
        _equipment(model, context3d, parent, f"Socket {name}", "IfcElectricAppliance",
                   cx + 0.3, cy, 0.9, 0.1, 0.1, 0.2, "socket",
                   room_ref=name, outlet_spacing_m=spacing),
    ]


def _duct(model, context3d, parent, name, x, y, z, length, width, height, net_height, along="x"):
    """An IfcDuctSegment (HVAC) with ArchCheckDuctParams. net_height_m is the
    clear headroom below the duct after it is installed."""
    boxes = [(0, 0, 0, length, width, height)] if along == "x" \
        else [(0, 0, 0, width, length, height)]
    duct = _element(model, context3d, parent, "IfcDuctSegment", name, x, y, z, boxes)
    _pset(model, duct, "ArchCheckDuctParams", {
        "duct_width_m": ("IfcReal", width),
        "duct_height_m": ("IfcReal", height),
        "net_height_m": ("IfcReal", net_height),
    })
    return duct


def _build_storey_elements(model, context3d, storey, floor_no, door_centers):
    """Physical elements (walls/slab/columns/beams/windows/stairs) for one storey."""
    el = []
    parent = storey.ObjectPlacement
    f = floor_no

    # floor slab (floor 1 doubles as the ground slab)
    el.append(_element(model, context3d, parent, "IfcSlab", f"FloorSlab {f}",
                       0, 0, -0.3, [(0, 0, 0, FOOT_W, FOOT_D, 0.3)]))
    # perimeter walls (0.3 thick, sit on the slab)
    el.append(_element(model, context3d, parent, "IfcWall", f"NorthWall {f}",
                       0, -0.3, 0, [(0, 0, 0, FOOT_W, 0.3, WALL_H)]))
    el.append(_element(model, context3d, parent, "IfcWall", f"SouthWall {f}",
                       0, 8.5, 0, [(0, 0, 0, FOOT_W, 0.3, WALL_H)]))
    el.append(_element(model, context3d, parent, "IfcWall", f"WestWall {f}",
                       -0.3, 0, 0, [(0, 0, 0, 0.3, FOOT_D, WALL_H)]))
    el.append(_element(model, context3d, parent, "IfcWall", f"EastWall {f}",
                       FOOT_W, 0, 0, [(0, 0, 0, 0.3, FOOT_D, WALL_H)]))
    # partition walls between rooms (y 2.5..8.5)
    for x in (4, 10, 16, 22, 28, 34):
        el.append(_element(model, context3d, parent, "IfcWall", f"Partition {x} {f}",
                           x - 0.1, 2.5, 0, [(0, 0, 0, 0.2, 6.0, WALL_H)]))
    # corridor spine wall with door openings
    for i, (a, b) in enumerate(_spine_segments(door_centers)):
        el.append(_element(model, context3d, parent, "IfcWall", f"SpineWall {f}-{i}",
                           a, 2.4, 0, [(0, 0, 0, b - a, 0.2, WALL_H)]))
    # structural grid: columns + beams on the two grid lines
    colx = (0, 4, 10, 16, 22, 28, 34, 38)
    for x in colx:
        for y in (2.5, 8.5):
            el.append(_element(model, context3d, parent, "IfcColumn", f"Col {x},{y} {f}",
                               x - 0.2, y - 0.2, 0, [(0, 0, 0, 0.4, 0.4, STOREY_H)]))
    for y in (2.5, 8.5):
        for a, b in zip(colx, colx[1:]):
            el.append(_element(model, context3d, parent, "IfcBeam", f"Beam {a}-{b} {f}",
                               a, y - 0.15, 3.3, [(0, 0, 0, b - a, 0.3, 0.4)]))
    # per-room electrical equipment (lighting + socket) + a south-facade window
    for name, rtype, x, y, w, d in floor_rooms(f):
        cx, cy = (x + w / 2, y + d / 2 - 0.05) if rtype == "Corridor" else (x + w / 2, y + d / 2)
        el += _room_equipment(model, context3d, parent, name, rtype, cx, cy)
        if rtype == "Corridor":
            continue
        el.append(_element(model, context3d, parent, "IfcWindow", f"Window {name}",
                           x + w / 2 - 0.75, 8.5, 1.0, [(0, 0, 0, 1.5, 0.3, 1.2)]))
    # stairs in the two stairwells (12 treads over 3.6m rise)
    for cx, tag in ((2.0, "A"), (FOOT_W - 2.0, "B")):
        boxes = []
        for i in range(12):
            boxes.append((cx - 0.5, 2.5 + i * 0.5, i * 0.3, 1.0, 0.5, 0.3))
        el.append(_element(model, context3d, parent, "IfcStair", f"Stair {f}{tag}",
                           0, 0, 0, boxes))
    # MEP pipes (fire supply main + a drainage branch with a designed low slope
    # so the drainage rule has real data and an honest finding)
    el.append(_pipe(model, context3d, parent, f"FireMain {f}", 1.0, 2.3, 0.3, 36.0, 0.10, "fire", 0.0))
    el.append(_pipe(model, context3d, parent, f"FireBranch {f}", 6.0, 2.5, 0.3, 2.0, 0.08, "fire", 0.0, along="y"))
    el.append(_pipe(model, context3d, parent, f"Drain A {f}", 12.0, 2.5, 0.3, 4.0, 0.075, "drainage", slope_geom=0.008))
    el.append(_pipe(model, context3d, parent, f"Drain B {f}", 24.0, 2.5, 0.3, 4.0, 0.075, "drainage", slope=0.015))
    # a designed MEP-vs-structure clash: a supply pipe running straight through
    # the south beam line (y=8.5, z 3.3-3.7) so the clash check has real data
    el.append(_pipe(model, context3d, parent, f"ClashPipe {f}", 10.0, 8.5, 3.35, 4.0, 0.1, "supply", 0.0))
    # electrical equipment — DB A sits 0.25m from the fire main (clearance
    # violation by design), DB B + lights far away (pass)
    el.append(_equipment(model, context3d, parent, f"DB A {f}", "IfcElectricAppliance", 3.0, 2.45, 0.6, 0.4, 0.3, 1.0, "distribution", room_ref="Corridor", circuit_load_a=8.0, dist_to_water_m=4.0))
    el.append(_equipment(model, context3d, parent, f"DB B {f}", "IfcElectricAppliance", 20.0, 5.0, 0.6, 0.4, 0.3, 1.0, "distribution", room_ref="Office 201", circuit_load_a=12.0, dist_to_water_m=3.0))
    # HVAC ducts — main supply duct high enough (net 2.3m), one low-hanging
    # branch with net 2.0m (clear-height violation by design)
    el.append(_duct(model, context3d, parent, f"SupplyDuct {f}", 1.0, 1.5, 2.7, 36.0, 0.8, 0.4, 2.3))
    el.append(_duct(model, context3d, parent, f"DuctBranch {f}", 16.0, 3.5, 2.4, 4.0, 0.5, 0.4, 2.0))
    # roof slab on the top storey
    if f == 3:
        el.append(_element(model, context3d, parent, "IfcSlab", "RoofSlab",
                           0, 0, STOREY_H, [(0, 0, 0, FOOT_W, FOOT_D, 0.3)]))
    return el


def main():
    model = ifcopenshell.file(schema="IFC4")
    units = model.create_entity("IfcUnitAssignment", Units=[
        model.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE"),
        model.create_entity("IfcSIUnit", UnitType="AREAUNIT", Name="SQUARE_METRE")])
    context3d = model.create_entity(
        "IfcGeometricRepresentationContext", ContextType="Model", CoordinateSpaceDimension=3,
        Precision=1e-5, WorldCoordinateSystem=model.create_entity("IfcAxis2Placement3D"))
    model.create_entity("IfcGeometricRepresentationSubContext", ContextIdentifier="Body",
                        ContextType="Model", ParentContext=context3d)

    person = model.create_entity("IfcPerson", FamilyName="ArchCheck")
    org = model.create_entity("IfcOrganization", Name="ArchCheck Demo")
    pao = model.create_entity("IfcPersonAndOrganization", ThePerson=person, TheOrganization=org)
    app = model.create_entity("IfcApplication", ApplicationDeveloper=org, Version="1.0",
                              ApplicationFullName="ArchCheck IFC Gen", ApplicationIdentifier="archcheck")
    owner = model.create_entity("IfcOwnerHistory", OwningUser=pao, OwningApplication=app, State="READWRITE")

    project = model.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(),
                                  Name="ArchCheck Office Sample", OwnerHistory=owner,
                                  RepresentationContexts=[context3d], UnitsInContext=units)
    site = model.create_entity("IfcSite", GlobalId=ifcopenshell.guid.new(), Name="Site",
                               CompositionType="ELEMENT",
                               ObjectPlacement=_placement(model, None, 0, 0, 0),
                               Representation=_box_rep(model, context3d,
                                                       [(-10.0, -6.0, -0.6, 58.0, 21.0, 0.3)]))
    building = model.create_entity("IfcBuilding", GlobalId=ifcopenshell.guid.new(),
                                   Name="Office Building", CompositionType="ELEMENT",
                                   ObjectPlacement=_placement(model, site.ObjectPlacement, 0, 0, 0))
    model.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(),
                        RelatingObject=site, RelatedObjects=[building])
    model.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(),
                        RelatingObject=project, RelatedObjects=[site])

    # Building-level params (from the review engine's building_params)
    _pset(model, building, "ArchCheckBuildingParams", {
        "occupancy_type": ("IfcLabel", "office"),
        "total_floors": ("IfcInteger", 3),
        "ground_floor_exit_width_m": ("IfcReal", 3.6),
        "fire_pool_volume_m3": ("IfcReal", 216.0),
        "transformer_capacity_kw": ("IfcReal", 750.0),
        "emergency_power_duration_min": ("IfcReal", 60.0),
    })

    for fi in range(3):
        storey = model.create_entity("IfcBuildingStorey", GlobalId=ifcopenshell.guid.new(),
                                     Name=f"Floor {fi + 1}", CompositionType="ELEMENT",
                                     Elevation=fi * STOREY_H,
                                     ObjectPlacement=_placement(model, building.ObjectPlacement, 0, 0, fi * STOREY_H))
        model.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(),
                            RelatingObject=building, RelatedObjects=[storey])

        rooms = floor_rooms(fi + 1)
        spaces, elems, door_centers = [], [], []
        for name, rtype, x, y, w, d in rooms:
            space = _box_space(model, context3d, storey.ObjectPlacement, name, w, d)
            _pset(model, space, "ArchCheckParams", {"room_type": ("IfcLabel", rtype)})
            _pset(model, space, "Pset_SpaceCommon", {"Reference": ("IfcIdentifier", name)})
            _pset(model, space, "ArchCheckEEEParams", _room_eee_params(rtype))
            spaces.append(space)
            if rtype != "Corridor":
                door = _door(model, context3d, _placement(model, storey.ObjectPlacement, x + w / 2, 2.4, 0))
                elems.append(door)
                door_centers.append(x + w / 2)
                model.create_entity("IfcRelSpaceBoundary", GlobalId=ifcopenshell.guid.new(),
                                    RelatingSpace=space, RelatedBuildingElement=door,
                                    PhysicalOrVirtualBoundary="PHYSICAL",
                                    InternalOrExternalBoundary="INTERNAL")

        elems += _build_storey_elements(model, context3d, storey, fi + 1, door_centers)

        model.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(),
                            RelatingObject=storey, RelatedObjects=spaces)
        model.create_entity("IfcRelContainedInSpatialStructure", GlobalId=ifcopenshell.guid.new(),
                            RelatingStructure=storey, RelatedElements=elems)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(OUT))
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
