"""Report helper (English) - print everything ArchCheck reads from Lab.ifc.

Run (from project root):  python scripts/demo_read_lab_en.py
Same data as demo_read_lab.py, English labels for an English-language report.
"""
from collections import Counter

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bim.parser import parse_ifc

s = parse_ifc("bim/Lab.ifc")
f = s["floors"][0]
st = f["structure"]
pipes, fits, ducts = f["pipes"], f.get("pipe_fittings", []), f["ducts"]
normal = [p for p in pipes if p.get("diameter_m") and p["diameter_m"] >= 0.010]
debris = [p for p in pipes if p.get("diameter_m") and p["diameter_m"] < 0.010]
se = f.get("structural_elements", [])
clashes = f.get("clashes", [])
plan = f.get("plan_elements", [])

L = []
A = L.append
A("")
A("=" * 44)
A("Lab.ifc - extraction overview")
A("=" * 44)
A("")
A(f"Project: {s['project_name'] or '(unnamed)'}   File: {s['file_name']}   schema: IFC4")
A(f"Storeys {s['storey_count']} | Rooms {s['total_rooms']} | Footprint {f.get('footprint_area_sqm', 0)} m2")
A("")
A("ARCHITECTURE / STRUCTURE")
A(f"  Elements    wall {st['walls']} | door {st['doors']} | window {st['windows']}"
  f" | column {st['columns']} | slab {st['slabs']}   (beam/stair/ramp 0)")
A(f"  Column sections (m)  {st['column_sections'][0]} etc., {len(st['column_sections'])} kinds")
A(f"  Door widths (m)      {sorted(st['door_widths_m'])}")
A(f"  Slab thickness (m)   {st['slab_thicknesses']}")
if se:
    n_col = sum(1 for e in se if e['element_type'] == 'column')
    n_sla = sum(1 for e in se if e['element_type'] == 'slab')
    A(f"  Structural elems     column {n_col} | slab {n_sla}")
    A(f"    e.g. column: {se[1]['section_min_m']}x{se[1]['section_max_m']}m, "
      f"vol {se[1]['volume_m3']}m3, {se[1]['material']}")
    A(f"    e.g. slab:   thk {se[3]['thickness_m']}m, vol {se[3]['volume_m3']}m3, "
      f"{se[3]['material']}")
A(f"  Material volume {st['material_volumes']} (m3)")
A(f"  Total structural vol {st['structural_volume_m3']} m3")
A("")
A("MEP DISTRIBUTION ELEMENTS")
A(f"  Pipe {len(pipes)} | Fitting {len(fits)} | Duct {len(ducts)}")
A("")
A("  - Pipe field coverage")
A(f"      diameter_m   {sum(1 for p in pipes if p.get('diameter_m'))}/173"
  f"   range {min(p['diameter_m'] for p in normal)*1000:.0f}"
  f"~{max(p['diameter_m'] for p in normal)*1000:.0f}mm")
A(f"      length_m     {sum(1 for p in pipes if p.get('length_m') is not None)}/173"
  f"   total {sum(p['length_m'] for p in pipes):.0f}m")
A(f"      slope        {sum(1 for p in pipes if p.get('slope') is not None)}/173")
A(f"      material     {sum(1 for p in pipes if p.get('material'))}/173"
  f" = {sorted(set(p['material'] for p in pipes))}")
A(f"      pipe_type    {0}/173   (file has no system tags -> unknown)")
A(f"      -- debris (dia<10mm) {len(debris)} - modelled junk, flagged")
A("")
A("  - Fitting field coverage")
A(f"      type {dict(Counter(pf['fitting_type'] for pf in fits))}")
A(f"      size {sum(1 for pf in fits if pf.get('size_m'))}/135"
  f"   material {sorted(set(pf['material'] for pf in fits))}")
A("")
A("  - Duct field coverage")
A(f"      width {sum(1 for d in ducts if d.get('duct_width_m'))}/108"
  f"   height {sum(1 for d in ducts if d.get('duct_height_m'))}/108")
A(f"      length {sum(1 for d in ducts if d.get('length_m') is not None)}/108"
  f"   material {sorted(set(d['material'] for d in ducts))}")
A("")
A("FURTHER ANALYSIS")
if clashes:
    n_conf = sum(1 for c in clashes if c.get("confirmed"))
    A(f"  MEP x structure clashes {len(clashes)}"
      f" ({n_conf} confirmed by geometry) - e.g. pipe through {clashes[0]['type']},"
      f" embed {clashes[0]['depth']}m")
A(f"  Plan-element bboxes {len(plan)} (for plan rendering: "
  f"{dict(Counter(p['kind'] for p in plan))})")
A("")
A("QA")
A(f"  Health score {s['qa']['score']}/100"
  f" | {len(s['qa']['entity_coverage']['handled'])} element types read, 0 unrecognised")
A("")
print("\n".join(L))
