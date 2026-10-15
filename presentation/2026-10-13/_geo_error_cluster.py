# -*- coding: utf-8 -*-
"""聚类 crosscheck 几何尺寸维度的错误：按模型×构件类×字段、偏差模式分组。"""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "output" / "crosscheck_v6"

def fnum(s):
    try:
        return float(str(s).replace(",", "").strip())
    except Exception:
        return None

rows = []
for p in sorted(D.glob("*_crosscheck.csv")):
    model = p.name.replace("_crosscheck.csv", "")
    with open(p, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append((model, r))

geo = [(m, r) for m, r in rows if r["dimension"] == "几何尺寸" and r["verdict"] == "✗"]
print(f"几何错误总行数: {len(geo)}\n")

# 1) 模型 × 构件类
by_model = Counter(m for m, _ in geo)
print("== 按模型 ==")
for m, c in by_model.most_common():
    print(f"  {c:5d}  {m}")

by_cat = Counter(r["category"] for _, r in geo)
print("\n== 按构件类 ==")
for c, n in by_cat.most_common():
    print(f"  {n:5d}  {c}")

by_field = Counter(r["field"] for _, r in geo)
print("\n== 按字段 ==")
for c, n in by_field.most_common(15):
    print(f"  {n:5d}  {c}")

by_mc = Counter((r["category"], r["field"]) for _, r in geo)
print("\n== 构件类 × 字段 (top 20) ==")
for (cat, fld), n in by_mc.most_common(20):
    print(f"  {n:5d}  {cat:14s} {fld}")

# 2) 偏差模式：比值 = extracted/truth
buckets = Counter()
examples = defaultdict(list)
for m, r in geo:
    t, e = fnum(r["truth_value"]), fnum(r["extracted_value"])
    if t is None or e is None or t == 0:
        tag = "不可解析/0真值"
    else:
        ratio = e / t
        if abs(ratio - 1) < 0.05: tag = "≈1x(容差边界)"
        elif 0.85 < ratio < 1.15: tag = "1.15-1.5x 或 0.67-0.85x"
        elif ratio > 50 or ratio < 0.02: tag = "单位级偏差(>50x/<0.02x)"
        elif ratio > 1.8: tag = "明显偏大(>1.8x)"
        elif ratio < 0.55: tag = "明显偏小(<0.55x)"
        else: tag = "中等偏差(1.15-1.8x / 0.55-0.67x)"
    buckets[tag] += 1
    if len(examples[tag]) < 4:
        examples[tag].append(f'{m[:18]}|{r["category"]}|{r["field"]}|truth={r["truth_value"]}|ext={r["extracted_value"]}')

print("\n== 偏差模式 ==")
for tag, n in buckets.most_common():
    print(f"  {n:5d}  {tag}")
    for ex in examples[tag]:
        print(f"          e.g. {ex}")

# 3) root_cause 文本聚类（取前缀关键词）
rc = Counter()
for _, r in geo:
    msg = r["root_cause"]
    for kw in ["斜", "bbox", "PCA", "Extrusion", "Qto", "单位", "world_scale",
               "开口", "opening", "轴", "截面", "profile", "厚度", "长度"]:
        if kw in msg:
            rc[kw] += 1
print("\n== root_cause 关键词命中 ==")
for k, n in rc.most_common():
    print(f"  {n:5d}  {k}")
print("\n样例 root_cause 文本：")
for _, r in geo[:0]:
    pass
seen = set()
for _, r in geo:
    msg = r["root_cause"][:80]
    key = msg[:30]
    if key not in seen:
        seen.add(key)
        print("  -", msg)
    if len(seen) >= 15:
        break
