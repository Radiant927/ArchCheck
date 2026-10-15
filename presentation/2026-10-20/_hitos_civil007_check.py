# -*- coding: utf-8 -*-
"""判定 CIVIL-007（房间无疏散出口）真伪：房间 hull 到最近门 bbox 的距离。"""
import sys, json
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))
from bim.parser import parse_ifc

IFC = HERE / "bim/test-suites/real-project/HITOS-Large-Building_IFC2x3.ifc"
s = parse_ifc(str(IFC), force_plan=True)
issues = json.load(open(Path(__file__).resolve().parent / "_hitos_review/all_issues.json",
                        encoding="utf-8"))
c7 = {(i.get("floor_name"), i.get("location")) for i in issues if i.get("rule_id") == "CIVIL-007"}
c7_names = {loc for _, loc in c7}


def pt_seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def hull_door_dist(hull, doors):
    # door passed as bbox rect; sample its perimeter; distance to hull polygon
    best = 1e9
    n = len(hull)
    for d in doors:
        x0, y0, x1, y1 = d[0], d[1], d[2], d[3]
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1),
               ((x0 + x1) / 2, y0), ((x0 + x1) / 2, y1),
               (x0, (y0 + y1) / 2), (x1, (y0 + y1) / 2)]
        for px, py in pts:
            for i in range(n):
                ax, ay = hull[i]
                bx, by = hull[(i + 1) % n]
                best = min(best, pt_seg_dist(px, py, ax, ay, bx, by))
    return best


print(f"CIVIL-007 房间数: {len(c7)}")
rows = []
for fl in s["floors"]:
    fname = fl.get("floor_name")
    doors = [tuple(p["bbox"]) for p in fl.get("plan_elements", []) if p.get("kind") == "door"]
    for r in fl.get("rooms", []):
        if r.get("name") in c7_names and r.get("hull"):
            d = hull_door_dist(r["hull"], doors) if doors else None
            rows.append((fname, r.get("name"), r.get("type"), r.get("room_area_sqm"),
                         len(doors), d))

rows.sort(key=lambda x: (x[5] if x[5] is not None else 9e9))
for thr in (0.5, 1.0, 2.0):
    near = sum(1 for *_, d in rows if d is not None and d < thr)
    print(f"匹配到 hull 的: {len(rows)} / {len(c7)}  |  最近门框 < {thr}m（疑似误报 FP）: {near}")
print(f"最近门框 >=2.0m 或 无门: {sum(1 for *_, d in rows if d is None or d >= 2.0)}")
print("\nfloor | room | type | area | #doors | dist_to_nearest_door")
for f, nm, t, a, nd, d in rows[:60]:
    ds = f"{d:.2f}" if d is not None else "no-door"
    print(f"  {str(f):8s} {str(nm):12s} {str(t):10s} {str(a):>7} {nd:>3d}  {ds}")

import csv as _csv
with open(Path(__file__).resolve().parent / "_hitos_review/civil007_dist.csv",
          "w", newline="", encoding="utf-8-sig") as fh:
    w = _csv.writer(fh)
    w.writerow(["floor", "room", "type", "area", "n_doors", "dist_to_nearest_doorframe_m"])
    for f, nm, t, a, nd, d in rows:
        w.writerow([f or "", nm, t, a, nd, f"{d:.3f}" if d is not None else ""])
print("\nwrote civil007_dist.csv")
