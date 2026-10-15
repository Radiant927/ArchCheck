# -*- coding: utf-8 -*-
"""HITOS crosscheck 错误聚类：按 维度×类×字段、偏差比值、root_cause 分组定位根因。"""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
D = HERE.parents[1] / "output" / "hitos_accuracy_2026-10" / "before"


def fnum(s):
    try:
        return float(str(s).replace(",", "").strip())
    except Exception:
        return None


rows = []
for p in sorted(D.glob("*_crosscheck.csv")):
    with open(p, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(r)

print(f"总行数: {len(rows)}")

by_dim = Counter(r["dimension"] for r in rows)
print("\n== 按维度 ==")
for k, n in by_dim.most_common():
    print(f"  {n:5d}  {k}")

by_v = Counter(r["verdict"] for r in rows)
print("\n== 按判定 ==")
for k, n in by_v.most_common():
    print(f"  {n:5d}  {k}")

# 计数维度（类整体）
print("\n== 计数维度（类整体：真值 vs 提取） ==")
for r in rows:
    if r["dimension"] == "计数" and r["field"] == "计数_类整体":
        t, e = fnum(r["truth_value"]), fnum(r["extracted_value"])
        flag = "OK" if r["verdict"] == "✓" else "!!"
        print(f"  {flag} {r['category']:10s} truth={t:>6.0f} ext={e:>6.0f}"
              f"  ratio={e/t if t else 0:.2f}")

# 漏读 / 多读 明细
miss = [r for r in rows if r["verdict"] in ("漏", "✗") and "漏" in r["root_cause"]]
multi = [r for r in rows if r["verdict"] in ("多",) or "多读" in r["root_cause"]]
print(f"\n== 漏读行 {len(miss)} / 多读行 {len(multi)} ==")
mc = Counter(r["category"] for r in miss)
print("  漏读 按类:", dict(mc.most_common()))
mc2 = Counter(r["category"] for r in multi)
print("  多读 按类:", dict(mc2.most_common()))

# 几何尺寸错误
geo = [r for r in rows if r["dimension"] == "几何尺寸" and r["verdict"] == "✗"]
print(f"\n== 几何尺寸错误行 {len(geo)} ==")
print("  按类:", dict(Counter(r["category"] for r in geo).most_common()))
print("  按字段:", dict(Counter(r["field"] for r in geo).most_common(20)))

# 几何 类×字段
print("\n  == 几何 类×字段 (top 25) ==")
for (cat, fld), n in Counter((r["category"], r["field"]) for r in geo).most_common(25):
    print(f"    {n:5d}  {cat:12s} {fld}")

# 偏差模式
buckets = Counter()
examples = defaultdict(list)
for r in geo:
    t, e = fnum(r["truth_value"]), fnum(r["extracted_value"])
    if t is None or e is None or t == 0:
        tag = "不可解析/0真值"
    else:
        ratio = e / t
        if abs(ratio - 1) < 0.05:
            tag = "≈1x(容差边界)"
        elif ratio > 50 or ratio < 0.02:
            tag = "单位级偏差(>50x/<0.02x)"
        elif ratio > 1.8:
            tag = "明显偏大(>1.8x)"
        elif ratio < 0.55:
            tag = "明显偏小(<0.55x)"
        else:
            tag = "中等偏差"
    buckets[tag] += 1
    if len(examples[tag]) < 5:
        examples[tag].append(
            f'{r["category"]}|{r["field"]}|truth={r["truth_value"]}|ext={r["extracted_value"]}'
            f'|rc={r["root_cause"][:40]}')

print("\n== 几何偏差模式 ==")
for tag, n in buckets.most_common():
    print(f"  {n:5d}  {tag}")
    for ex in examples[tag]:
        print(f"          e.g. {ex}")

# root_cause 文本聚类
print("\n== root_cause 去重样例 ==")
seen = set()
for r in rows:
    if r["verdict"] == "✓" or not r["root_cause"].strip():
        continue
    key = r["root_cause"][:34]
    if key in seen:
        continue
    seen.add(key)
    print(f"  [{r['category']}/{r['dimension']}] {r['root_cause'][:90]}")
    if len(seen) >= 30:
        break
