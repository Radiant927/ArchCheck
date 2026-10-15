# -*- coding: utf-8 -*-
"""互检平面标注 viewer — 把逐构件对/错/漏标到平面图上（静态图，A5 第一版）。

读一个 IFC + 它的 crosscheck CSV，按 GlobalId 把每个物理构件（墙/柱/梁/板/窗/门/
栏杆）的对错判定画到该层的真实 footprint 平面上：✓ 绿、✗ 红、漏 橙、多 紫、
未比对灰。一张图看清"哪对哪错在哪"。

用法:
  python scripts/render_crosscheck_annotated.py <ifc> \
      --crosscheck output/crosscheck_v4/<model>_crosscheck.csv \
      --out output/crosscheck_viewer
"""
import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bim.parser import parse_ifc, build_review_data      # noqa: E402
from core import drawing                                  # noqa: E402
from PIL import Image, ImageDraw, ImageFont               # noqa: E402


def _font(size):
    for name in ("msyh.ttc", "simhei.ttf", "simsun.ttc", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def compose_overview(imgs, counts, out_path, model_name):
    """Tile per-floor annotated plans into one board with a header + stats."""
    cols = min(2, max(1, len(imgs)))
    rows = (len(imgs) + cols - 1) // cols
    tw, th = 900, 600                       # tile size
    head_h = 110
    pad = 20
    W = pad + cols * (tw + pad)
    H = head_h + pad + rows * (th + pad)
    board = Image.new("RGB", (W, H), (245, 246, 248))
    d = ImageDraw.Draw(board)
    d.rectangle([0, 0, W, head_h - 10], fill=(30, 35, 45))
    d.text((28, 14), f"互检平面标注总览 · {model_name}", fill=(240, 245, 250),
           font=_font(34))
    stat = (f"✓ 全对 {counts['✓']}    ✗ 读错 {counts['✗']}    "
            f"漏读 {counts['漏']}    多读 {counts['多']}    （共 {len(imgs)} 层）")
    d.text((30, 62), stat, fill=(200, 210, 220), font=_font(22))
    for i, im in enumerate(imgs):
        r, c = divmod(i, cols)
        x = pad + c * (tw + pad)
        y = head_h + pad + r * (th + pad)
        board.paste(im.convert("RGB").resize((tw, th)), (x, y))
        d.rectangle([x, y, x + tw, y + th], outline=(160, 168, 178), width=2)
    board.save(out_path)
    return out_path


def load_verdict_map(csv_path):
    """GlobalId -> {"name", "category", "fields": [(field, truth, extracted, verdict)]}."""
    vmap = {}
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            gid = row.get("global_id", "")
            if not gid:
                continue
            e = vmap.setdefault(gid, {"name": row.get("name", ""),
                                      "category": row.get("category", ""),
                                      "fields": []})
            e["fields"].append((row.get("field", ""), row.get("truth_value", ""),
                                row.get("extracted_value", ""), row.get("verdict", "?")))
    return vmap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ifc")
    ap.add_argument("--crosscheck", required=True, help="crosscheck CSV path")
    ap.add_argument("--out", default="output/crosscheck_viewer")
    args = ap.parse_args()

    ifc_path = Path(args.ifc)
    csv_path = Path(args.crosscheck)
    outdir = Path(args.out)
    if not outdir.is_absolute():
        outdir = ROOT / outdir
    outdir.mkdir(parents=True, exist_ok=True)

    model_name = ifc_path.stem
    print(f"解析 {ifc_path.name} …")
    bdata = build_review_data(parse_ifc(str(ifc_path)))
    vmap = load_verdict_map(csv_path)
    print(f"crosscheck 构件数：{len(vmap)}")

    # aggregate stats for the summary page
    tot = defaultdict(int)
    for e in vmap.values():
        vs = [f[3] for f in e["fields"]]
        worst = max(vs, key=lambda v: {"✗": 3, "漏": 2, "多": 2, "✓": 1}.get(v, 0)) if vs else "?"
        tot[worst] += 1

    outputs = []
    imgs = []
    for i, f in enumerate(bdata["floors"]):
        rooms = f.get("rooms", [])
        pe = f.get("plan_elements", [])
        if not rooms and not pe:
            continue
        floor_name = f.get("floor_name", f"F{i+1}")
        img = drawing.render_crosscheck_plan(
            rooms, pe, vmap, floor_name=floor_name,
            subtitle=f"{model_name}")
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in floor_name)
        p = outdir / f"{model_name}_{i+1}_{safe}.png"
        img.save(p)
        outputs.append(p)
        imgs.append(img)
        print(f"  → {p.name}  (rooms {len(rooms)}, elements {len(pe)})")

    # combined overview board
    board_path = None
    if imgs:
        board_path = outdir / f"{model_name}_总览.png"
        compose_overview(imgs, tot, board_path, model_name)
        print(f"  → {board_path.name}  (总览板)")

    # summary
    lines = [f"# 互检平面标注图 · {model_name}\n",
             f"- crosscheck 构件：{len(vmap)}",
             f"- ✓ 全对：{tot['✓']}   ✗ 有错：{tot['✗']}   漏读：{tot['漏']}   多读：{tot['多']}\n",
             "## 产出的图层\n"]
    if board_path:
        lines.append(f"- `{board_path.name}` — 全楼总览板")
    for p in outputs:
        lines.append(f"- `{p.name}`")
    lines.append("")
    (outdir / f"{model_name}_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n汇总：{outdir / (model_name + '_summary.md')}")


if __name__ == "__main__":
    main()
