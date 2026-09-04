"""Generate a synthetic IFC4 file exercising pipe port topology.

Purpose: validation fixture for the extractor's topology reader, since no real
MEP IFC on hand carries IfcRelConnectsPorts / IfcDistributionPort data.

Layout (all coordinates metres, along the X axis):
    A [0..3] -- B [3..6] -- C [6..9]      (three pipe segments end-to-end)
Each segment carries two IfcDistributionPorts at its ends. Two
IfcRelConnectsPorts join A→B and B→C, so the graph is the chain A-B-C.
All three pipes belong to system "Chilled Water" via IfcRelAssignsToGroup.
One pipe fitting (union) sits between B and C to prove fittings join too.

Output: bim/samples/topology_chain.ifc
"""
import ifcopenshell
import ifcopenshell.guid
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "bim" / "samples" / "topology_chain.ifc"


def _guid():
    return ifcopenshell.guid.new()


def _owner(model):
    person = model.create_entity("IfcPerson", GivenName="ArchCheck")
    org = model.create_entity("IfcOrganization", Name="ArchCheck Test")
    who = model.create_entity("IfcPersonAndOrganization", ThePerson=person, TheOrganization=org)
    app = model.create_entity("IfcApplication", ApplicationDeveloper=org,
                              Version="1.0", ApplicationFullName="ArchCheck",
                              ApplicationIdentifier="AC")
    return model.create_entity("IfcOwnerHistory", OwningUser=who,
                               OwningApplication=app, ChangeAction="ADDED")


def _placement(model, parent, x):
    pt = model.create_entity("IfcCartesianPoint", [x, 0.0, 0.0])
    ax = model.create_entity("IfcAxis2Placement3D", Location=pt)
    return model.create_entity("IfcLocalPlacement", PlacementRelTo=parent,
                               RelativePlacement=ax)


def build():
    model = ifcopenshell.file(schema="IFC4")
    oh = _owner(model)
    proj = model.create_entity("IfcProject", GlobalId=_guid(), OwnerHistory=oh,
                               Name="Topology Chain", RepresentationContexts=None,
                               UnitsInContext=None)
    # project < building < storey (so pipes have a spatial parent)
    site = model.create_entity("IfcSite", GlobalId=_guid(), OwnerHistory=oh)
    bldg = model.create_entity("IfcBuilding", GlobalId=_guid(), OwnerHistory=oh)
    storey = model.create_entity("IfcBuildingStorey", GlobalId=_guid(),
                                 OwnerHistory=oh, Name="Level 1", Elevation=0.0)
    model.create_entity("IfcRelAggregates", GlobalId=_guid(), OwnerHistory=oh,
                        RelatingObject=proj, RelatedObjects=[site])
    model.create_entity("IfcRelAggregates", GlobalId=_guid(), OwnerHistory=oh,
                        RelatingObject=site, RelatedObjects=[bldg])
    model.create_entity("IfcRelAggregates", GlobalId=_guid(), OwnerHistory=oh,
                        RelatingObject=bldg, RelatedObjects=[storey])

    # --- three pipe segments with ports at each end ---
    segments = []   # (entity, [ports])
    xs = [(0.0, 3.0), (3.0, 6.0), (6.0, 9.0)]
    for i, (x0, x1) in enumerate(xs):
        seg = model.create_entity("IfcPipeSegment", GlobalId=_guid(),
                                  OwnerHistory=oh, Name=f"Pipe {chr(65+i)}",
                                  ObjectPlacement=_placement(model, storey, x0))
        # two ports: SINK at x0 (inlet), SOURCE at x1 (outlet)
        p_in = model.create_entity("IfcDistributionPort", GlobalId=_guid(),
                                   OwnerHistory=oh, Name=f"Pipe {chr(65+i)}-in",
                                   FlowDirection="SINK")
        p_out = model.create_entity("IfcDistributionPort", GlobalId=_guid(),
                                    OwnerHistory=oh, Name=f"Pipe {chr(65+i)}-out",
                                    FlowDirection="SOURCE")
        for p in (p_in, p_out):
            model.create_entity("IfcRelConnectsPortToElement", GlobalId=_guid(),
                                OwnerHistory=oh, RelatingPort=p, RelatedElement=seg)
        segments.append((seg, (p_in, p_out)))

    # --- one union fitting joining Pipe B outlet and Pipe C inlet ---
    union = model.create_entity("IfcPipeFitting", GlobalId=_guid(), OwnerHistory=oh,
                                Name="Union BC", ObjectPlacement=_placement(model, storey, 6.0))
    u_in = model.create_entity("IfcDistributionPort", GlobalId=_guid(), OwnerHistory=oh,
                               Name="Union BC-in", FlowDirection="SINK")
    u_out = model.create_entity("IfcDistributionPort", GlobalId=_guid(), OwnerHistory=oh,
                                Name="Union BC-out", FlowDirection="SOURCE")
    for p in (u_in, u_out):
        model.create_entity("IfcRelConnectsPortToElement", GlobalId=_guid(),
                            OwnerHistory=oh, RelatingPort=p, RelatedElement=union)
    seg_a, (a_in, a_out) = segments[0]
    seg_b, (b_in, b_out) = segments[1]
    seg_c, (c_in, c_out) = segments[2]

    # storey contains the three pipe segments + the union
    model.create_entity("IfcRelContainedInSpatialStructure", GlobalId=_guid(),
                        OwnerHistory=oh,
                        RelatingStructure=storey,
                        RelatedElements=[seg_a, seg_b, seg_c, union])

    # A.out connects to B.in
    model.create_entity("IfcRelConnectsPorts", GlobalId=_guid(), OwnerHistory=oh,
                        Name="A-B", RelatingPort=a_out, RelatedPort=b_in)
    # B.out connects to union.in
    model.create_entity("IfcRelConnectsPorts", GlobalId=_guid(), OwnerHistory=oh,
                        Name="B-union", RelatingPort=b_out, RelatedPort=u_in)
    # union.out connects to C.in
    model.create_entity("IfcRelConnectsPorts", GlobalId=_guid(), OwnerHistory=oh,
                        Name="union-C", RelatingPort=u_out, RelatedPort=c_in)

    # --- one distribution system holding all pipes + the fitting ---
    sys_ = model.create_entity("IfcDistributionSystem", GlobalId=_guid(),
                               OwnerHistory=oh, Name="Chilled Water",
                               PredefinedType="CHILLEDWATER")
    model.create_entity("IfcRelAssignsToGroup", GlobalId=_guid(), OwnerHistory=oh,
                        RelatingGroup=sys_,
                        RelatedObjects=[seg_a, seg_b, seg_c, union])

    model.write(str(OUT))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    build()
