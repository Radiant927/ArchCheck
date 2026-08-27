# -*- coding: utf-8 -*-
"""COBie 导出（台阶⑥ · 施工交付数据）。输出 COBie 核心 CSV（Facility/Floor/Space），
可对接 FM/资产管理系统。

用法:
  python scripts/export_cobie.py bim/samples/office_3f.ifc -o output/cobie.csv
"""
import argparse
import csv
import io
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bim.parser import parse_ifc  # noqa: E402


def export_cobie(path, out):
    m = parse_ifc(path, max_floors=3, max_rooms_per_floor=6)
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    rows = []
    # Facility
    rows.append(["Sheet", "Facility", "", ""])
    rows.append(["Name", "CreatedBy", "CreatedOn", "Description"])
    rows.append([m.get("project_name") or "Building", "ArchCheck", now, "ArchCheck review"])
    rows.append([])
    # Floor
    rows.append(["Sheet", "Floor", "", ""])
    rows.append(["Name", "CreatedBy", "CreatedOn", "FloorName", "Description"])
    for f in m["floors"]:
        rows.append([f["name"], "ArchCheck", now, f["name"],
                     f"elevation {f.get('elevation_m')} m · footprint {f.get('footprint_area_sqm')} m²"])
    rows.append([])
    # Space
    rows.append(["Sheet", "Space", "", ""])
    rows.append(["Name", "CreatedBy", "CreatedOn", "FloorName", "SpaceName", "SpaceType", "Area"])
    for f in m["floors"]:
        for r in f["rooms"]:
            rows.append([r["name"], "ArchCheck", now, f["name"], r["name"],
                         r.get("type", "Unknown"), r.get("room_area_sqm", "")])
    out = Path(out)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerows(rows)
    return len(m["floors"])


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("ifc")
    ap.add_argument("-o", "--out", default=str(ROOT / "output" / "cobie.csv"))
    args = ap.parse_args()
    n = export_cobie(args.ifc, args.out)
    print(f"已导出 {args.out}（{n} 层 · 含 Facility/Floor/Space 表）")


if __name__ == "__main__":
    main()
