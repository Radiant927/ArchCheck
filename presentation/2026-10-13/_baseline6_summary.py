# -*- coding: utf-8 -*-
import csv, glob, sys
from collections import Counter
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

D = Path(__file__).resolve().parents[2] / "output" / "crosscheck_baseline6"
print(f"{'模型':16s} {'总行':>5s} {'✓':>5s} {'✗':>4s} {'漏':>3s} {'多':>3s} {'正确率':>7s}  几何✗ 计数✗")
for p in sorted(D.glob("*_crosscheck.csv")):
    name = p.name.replace("_crosscheck.csv", "")[:16]
    rows = list(csv.DictReader(open(p, encoding="utf-8-sig")))
    v = Counter(r["verdict"] for r in rows)
    ok, bad = v.get("✓", 0), v.get("✗", 0)
    miss, extra = v.get("漏", 0), v.get("多", 0)
    geo = sum(1 for r in rows if r["dimension"] == "几何尺寸" and r["verdict"] == "✗")
    cnt = sum(1 for r in rows if r["dimension"] == "计数" and r["verdict"] == "✗")
    tot = ok + bad
    rate = f"{ok/tot*100:.1f}%" if tot else "-"
    print(f"{name:16s} {len(rows):5d} {ok:5d} {bad:4d} {miss:3d} {extra:3d} {rate:>7s}  {geo:4d}  {cnt:4d}")

print("\n== 逐模型几何错误按构件类×字段 ==")
for p in sorted(D.glob("*_crosscheck.csv")):
    name = p.name.replace("_crosscheck.csv", "")[:16]
    rows = list(csv.DictReader(open(p, encoding="utf-8-sig")))
    geo = [r for r in rows if r["dimension"] == "几何尺寸" and r["verdict"] == "✗"]
    if not geo:
        continue
    c = Counter((r["category"], r["field"]) for r in geo)
    print(f"\n{name}: {len(geo)} 个几何错误")
    for (cat, fld), n in c.most_common(8):
        print(f"   {n:4d}  {cat:12s} {fld}")
    rc = Counter(r["root_cause"][:40] for r in geo)
    for msg, n in rc.most_common(4):
        print(f"         根因 x{n}: {msg}")
