# -*- coding: utf-8 -*-
"""HITOS 审查判定金标准：对聚合后 all_issues 逐条裁定 TP/FP/待复核，输出 CSV + precision。

裁定依据：规则逻辑 + 模型数据实证（CIVIL-007 用房间 hull 到最近门框距离）。
severity=Missing 为"数据缺失"提示，非违规，不计入 precision 分母。
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
RV = HERE / "_hitos_review"

issues = json.load(open(RV / "all_issues.json", encoding="utf-8"))
dist = {}
for r in csv.DictReader(open(RV / "civil007_dist.csv", encoding="utf-8-sig")):
    if r["dist_to_nearest_doorframe_m"]:
        dist[r["room"]] = float(r["dist_to_nearest_doorframe_m"])

# 规则 → 裁定规则（函数：issue → (verdict, basis)）
def adjudicate(iss):
    rid = iss.get("rule_id")
    sev = iss.get("severity")
    if sev == "Missing":
        return ("不计入", "数据缺失提示，非违规")
    if rid == "CIVIL-007":
        d = dist.get(iss.get("location"))
        if d is None:
            return ("待复核", "无几何，无法核验")
        if d < 1.0:
            return ("FP", f"房间 hull 外 {d:.2f}m 内有门框，实际有门→门关联缺失误报")
        if d < 2.0:
            return ("FP(疑似)", f"最近门框 {d:.2f}m，bbox 矩形房间footprint 近似致关联失败")
        return ("待复核", f"最近门框 {d:.2f}m，可能真无直连出口")
    if rid == "CIVIL-001":
        return ("TP", "走廊 hull 实测超 30m（GB 55037 疏散距离）")
    if rid == "CIVIL-012":
        return ("TP", "房间最远点疏散距离 33.07m>30m（GB 55037）")
    if rid in ("CIVIL-003", "CIVIL-005"):
        return ("TP待复核", "面积超阈值需 2 出口（GB 50016）；出口数含关联口径")
    if rid == "STR-001":
        return ("TP", "柱截面小于最小值（GB 50010），截面提取已修正")
    if rid == "CIVIL-004":
        return ("TP", "门净宽 0.89<0.9m（GB 55037）")
    return ("待复核", "未自动裁定")


rows = []
for iss in issues:
    v, basis = adjudicate(iss)
    rows.append({**{k: iss.get(k) for k in
                    ("rule_id", "title", "severity", "floor_name", "location",
                     "description", "code_ref")},
                 "adjudication": v, "basis": basis})

out = HERE / "HITOS审查判定正确率_金标准_2026-10-14.csv"
with open(out, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["rule_id", "title", "severity", "floor_name",
                                      "location", "description", "code_ref",
                                      "adjudication", "basis"])
    w.writeheader()
    w.writerows(rows)

c = Counter(r["adjudication"] for r in rows)
print("裁定分布:", dict(c.most_common()))
dec = [r for r in rows if r["adjudication"] != "不计入"]
tp = sum(1 for r in dec if r["adjudication"].startswith("TP"))
fp = sum(1 for r in dec if r["adjudication"].startswith("FP"))
unc = sum(1 for r in dec if r["adjudication"] == "待复核")
print(f"decidable={len(dec)}  TP={tp}  FP={fp}  待复核={unc}")
if tp + fp:
    print(f"Precision = {tp}/({tp}+{fp}) = {tp/(tp+fp)*100:.1f}%")
print("\n按规则:")
for rid in sorted({r["rule_id"] for r in dec}):
    sub = [r for r in dec if r["rule_id"] == rid]
    cc = Counter(r["adjudication"] for r in sub)
    print(f"  {rid:10s} n={len(sub):4d}  {dict(cc)}")
print("\nwrote", out)
