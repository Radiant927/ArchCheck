"""Generate a clean multi-storey office IFC sample for ArchCheck.

Builds a deterministic 3-storey office building with ifcopenshell:
- rooms with function-typed names (Corridor / Office / Meeting Room / Stairwell)
  so the type classifier is honest, plus extruded-box geometry (area extracted)
- one IfcDoor per room opening onto the corridor, each with
  Pset_DoorCommon.OverallWidth so the parser reads real door widths
- storeys + spaces wired through IfcRelAggregates / IfcRelContainedInSpatialStructure

Output: bim/samples/office_3f.ifc
"""
import math
import ifcopenshell
import ifcopenshell.guid
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "bim" / "samples" / "office_3f.ifc"

# per-storey layout: (name, type, x, y, w, d) in metres, corridor runs along y=0..2.5
def floor_rooms(floor_no):
    n = floor_no * 100
    rooms = [
        ("Corridor", "Corridor", 0.0, 0.0, 38.0, 2.5),
        (f"Stairwell {floor_no}A", "Stairwell", 0.0, 2.5, 4.0, 6.0),
        (f"Office {n + 1}", "Office", 4.0, 2.5, 6.0, 6.0),
        (f"Office {n + 2}", "Office", 10.0, 2.5, 6.0, 6.0),
        (f"Office {n + 3}", "Office", 16.0, 2.5, 6.0, 6.0),
        (f"Office {n + 4}", "Office", 22.0, 2.5, 6.0, 6.0),
        (f"Meeting Room {n + 5}", "Meeting Room", 28.0, 2.5, 6.0, 6.0),
        (f"Stairwell {floor_no}B", "Stairwell", 34.0, 2.5, 4.0, 6.0),
    ]
    return rooms


def _pt(model, x, y, z):
    return model.create_entity("IfcCartesianPoint", [float(x), float(y), float(z)])


def _placement(model, parent, x, y, z):
    return model.create_entity(
        "IfcLocalPlacement", PlacementRelTo=parent,
        RelativePlacement=model.create_entity("IfcAxis2Placement3D", Location=_pt(model, x, y, z)))


def _faceted_box_rep(model, context3d, w, d, h):
    """An IfcFacetedBrep box (this ifcopenshell build cannot process swept solids)."""
    P = [(0, 0, 0), (w, 0, 0), (w, d, 0), (0, d, 0),
         (0, 0, h), (w, 0, h), (w, d, h), (0, d, h)]
    pts = [model.create_entity("IfcCartesianPoint", [float(x), float(y), float(z)]) for x, y, z in P]
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


def _door(model, context3d, placement, width=0.9, height=2.1):
    door = model.create_entity("IfcDoor", GlobalId=ifcopenshell.guid.new(),
                               Name=f"Door {width}m", ObjectPlacement=placement,
                               OverallWidth=width, OverallHeight=height,
                               Representation=_faceted_box_rep(model, context3d, width, 0.2, height))
    _pset(model, door, "Pset_DoorCommon", {"OverallWidth": ("IfcReal", width),
                                           "OverallHeight": ("IfcReal", height)})
    return door


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
                               ObjectPlacement=_placement(model, None, 0, 0, 0))
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
                                     Elevation=fi * 3.6,
                                     ObjectPlacement=_placement(model, building.ObjectPlacement, 0, 0, fi * 3.6))
        model.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(),
                            RelatingObject=building, RelatedObjects=[storey])

        rooms = floor_rooms(fi + 1)
        spaces = []
        for name, rtype, x, y, w, d in rooms:
            space = _box_space(model, context3d, storey.ObjectPlacement, name, w, d)
            _pset(model, space, "ArchCheckParams", {"room_type": ("IfcLabel", rtype)})
            spaces.append(space)
            # door on the corridor wall (y = 2.5) for every room except the corridor itself
            if rtype != "Corridor":
                door = _door(model, context3d, _placement(model, storey.ObjectPlacement, x + w / 2, 2.5, 0))
                _pset(model, space, "Pset_SpaceCommon", {"Reference": ("IfcIdentifier", name)})
                _pset(model, door, "Pset_DoorCommon", {"OverallWidth": ("IfcReal", 0.9),
                                                       "OverallHeight": ("IfcReal", 2.1)})

        model.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(),
                            RelatingObject=storey, RelatedObjects=spaces)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(OUT))
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
