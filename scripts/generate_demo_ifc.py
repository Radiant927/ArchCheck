"""Generate a demo IFC file for ArchCheck.

Builds a 3-floor office building from data/demo_building_data.json using
ifcopenshell: spaces with extruded-box geometry (area derived from the
footprint), fire zones (IfcZone), and custom property sets that carry the
compliance parameters the review engine consumes.

Output: output/demo_building.ifc
"""
import json
import math
import ifcopenshell
import ifcopenshell.guid
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data" / "demo_building_data.json"
OUT = HERE / "output" / "demo_building.ifc"


def pset(model, entity, name, props):
    """Attach a property set (name -> {type, value}) to an entity."""
    values = []
    for key, (ptype, val) in props.items():
        nominal = model.create_entity(ptype, val)
        values.append(model.create_entity(
            "IfcPropertySingleValue", Name=key, NominalValue=nominal))
    ps = model.create_entity("IfcPropertySet", GlobalId=ifcopenshell.guid.new(),
                             Name=name, HasProperties=values)
    model.create_entity("IfcRelDefinesByProperties", GlobalId=ifcopenshell.guid.new(),
                        RelatingPropertyDefinition=ps, RelatedObjects=[entity])
    return ps


def box_space(model, context3d, parent_placement, name, w, d, h=3.0,
              offset=(0.0, 0.0)):
    """Create an IfcSpace with a rectangular extruded footprint."""
    origin = model.create_entity("IfcAxis2Placement3D",
                                 Location=model.create_entity(
                                     "IfcCartesianPoint", (offset[0], offset[1], 0.0)))
    placement = model.create_entity("IfcLocalPlacement",
                                    PlacementRelTo=parent_placement,
                                    RelativePlacement=origin)
    profile = model.create_entity("IfcRectangleProfileDef", ProfileType="AREA",
                                  XDim=w, YDim=d)
    solid = model.create_entity("IfcExtrudedAreaSolid", SweptArea=profile, Depth=h)
    rep = model.create_entity("IfcShapeRepresentation", ContextOfItems=context3d,
                              RepresentationIdentifier="Body",
                              RepresentationType="SweptSolid", Items=[solid])
    shape = model.create_entity("IfcProductDefinitionShape", Representations=[rep])
    space = model.create_entity("IfcSpace", GlobalId=ifcopenshell.guid.new(),
                                Name=name, ObjectType="Space",
                                CompositionType="ELEMENT",
                                ObjectPlacement=placement, Representation=shape)
    return space, w * d


def main():
    bdata = json.loads(DATA.read_text(encoding="utf-8"))
    model = ifcopenshell.file()
    schema = model.schema

    # Units + geometry context
    units = model.create_entity("IfcUnitAssignment", Units=[
        model.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE"),
        model.create_entity("IfcSIUnit", UnitType="AREAUNIT", Name="SQUARE_METRE")])
    context3d = model.create_entity(
        "IfcGeometricRepresentationContext",
        ContextType="Model", CoordinateSpaceDimension=3, Precision=1e-5,
        WorldCoordinateSystem=model.create_entity("IfcAxis2Placement3D"))

    # Owner history (minimal)
    person = model.create_entity("IfcPerson", FamilyName="ArchCheck")
    org = model.create_entity("IfcOrganization", Name="ArchCheck Demo")
    pao = model.create_entity("IfcPersonAndOrganization", ThePerson=person,
                              TheOrganization=org)
    app = model.create_entity("IfcApplication", ApplicationDeveloper=org,
                              Version="1.0", ApplicationFullName="ArchCheck IFC Gen",
                              ApplicationIdentifier="archcheck")
    owner = model.create_entity("IfcOwnerHistory", OwningUser=pao,
                                OwningApplication=app, State="READWRITE")

    # Project -> Site -> Building
    project = model.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(),
                                  Name=bdata.get("project_name", "Demo Building"),
                                  OwnerHistory=owner,
                                  RepresentationContexts=[context3d],
                                  UnitsInContext=units)
    site = model.create_entity("IfcSite", GlobalId=ifcopenshell.guid.new(),
                               Name="Site", CompositionType="ELEMENT",
                               ObjectPlacement=model.create_entity(
                                   "IfcLocalPlacement",
                                   PlacementRelTo=None,
                                   RelativePlacement=model.create_entity(
                                       "IfcAxis2Placement3D")))
    building = model.create_entity("IfcBuilding", GlobalId=ifcopenshell.guid.new(),
                                   Name="Office Building", CompositionType="ELEMENT",
                                   ObjectPlacement=model.create_entity(
                                       "IfcLocalPlacement",
                                       PlacementRelTo=site.ObjectPlacement,
                                       RelativePlacement=model.create_entity(
                                           "IfcAxis2Placement3D")))
    model.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(),
                        RelatingObject=site, RelatedObjects=[building])
    model.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(),
                        RelatingObject=project, RelatedObjects=[site])

    # Building-level compliance params as a property set on the building
    bp = bdata.get("building_params", {})
    pset(model, building, "ArchCheckBuildingParams", {
        "occupancy_type": ("IfcLabel", bp.get("occupancy_type", "office")),
        "total_floors": ("IfcInteger", int(bp.get("total_floors", 3))),
        "ground_floor_exit_width_m": ("IfcReal", float(bp.get("ground_floor_exit_width_m", 2.4))),
        "fire_pool_volume_m3": ("IfcReal", float(bp.get("fire_pool_volume_m3", 160))),
        "transformer_capacity_kw": ("IfcReal", float(bp.get("transformer_capacity_kw", 650))),
        "emergency_power_duration_min": ("IfcReal", float(bp.get("emergency_power_duration_min", 60))),
    })

    # Storeys + spaces
    floors = bdata.get("floors", [])
    for fi, floor in enumerate(floors):
        storey = model.create_entity("IfcBuildingStorey",
                                     GlobalId=ifcopenshell.guid.new(),
                                     Name=floor.get("floor_name", f"F{fi+1}"),
                                     CompositionType="ELEMENT",
                                     ObjectPlacement=model.create_entity(
                                         "IfcLocalPlacement",
                                         PlacementRelTo=building.ObjectPlacement,
                                         RelativePlacement=model.create_entity(
                                             "IfcAxis2Placement3D",
                                             Location=model.create_entity(
                                                 "IfcCartesianPoint",
                                                 (0.0, 0.0, float(fi) * 3.6)))))
        pset(model, storey, "ArchCheckFloorParams",
             {"floor_id": ("IfcLabel", floor.get("floor_id", f"F{fi+1}"))})
        model.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(),
                            RelatingObject=building, RelatedObjects=[storey])

        spaces = []
        cx = 0.0
        for room in floor.get("rooms", []):
            area = float(room.get("room_area_sqm", 20))
            # rectangular footprint approximating the area
            if room.get("type") == "Corridor":
                w, d = round(area / 3.0, 1), 3.0
            else:
                w = round(math.sqrt(area) * 1.2, 1)
                d = round(area / w, 1)
            space, geom_area = box_space(model, context3d, storey.ObjectPlacement,
                                         room["name"], w, d, offset=(cx, 0.0))
            cx += w + 1.0
            pset(model, space, "ArchCheckParams", {
                "room_type": ("IfcLabel", room.get("type", "Office")),
                "room_area_sqm": ("IfcReal", geom_area),
                "exit_count": ("IfcInteger", int(room.get("exit_count", 1))),
                "door_width_m": ("IfcReal", float(room.get("door_width_m", 0.9))),
                "has_emergency_light": ("IfcBoolean", bool(room.get("has_emergency_light", False))),
                "dist_to_water_m": ("IfcReal", float(room.get("dist_to_water_m", 5.0))),
                "circuit_load_a": ("IfcReal", float(room.get("circuit_load_a", 10))),
                "outlet_spacing_m": ("IfcReal", float(room.get("outlet_spacing_m", 5.0))),
                "corridor_length_m": ("IfcReal", float(room.get("corridor_length_m", 0))),
            })
            spaces.append(space)

        model.create_entity("IfcRelContainedInSpatialStructure",
                            GlobalId=ifcopenshell.guid.new(),
                            RelatingStructure=storey, RelatedElements=spaces)

        # Fire zones on this floor
        for zone in floor.get("fire_zones", []):
            izone = model.create_entity("IfcZone", GlobalId=ifcopenshell.guid.new(),
                                        Name=zone.get("name", "Fire Zone"))
            pset(model, izone, "ArchCheckZoneParams", {
                "zone_id": ("IfcLabel", zone.get("id", "")),
                "fire_zone_area_sqm": ("IfcReal", float(zone.get("fire_zone_area_sqm", 0))),
            })
            members = [s for s in spaces if s.Name in zone.get("rooms", [])]
            model.create_entity("IfcRelAssignsToGroup", GlobalId=ifcopenshell.guid.new(),
                                RelatingGroup=izone, RelatedObjects=members)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    model.write(str(OUT))
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
