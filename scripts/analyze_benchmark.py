"""Generate T/Q/P practicality scorecards + Q4/P3 comparison reports.

Reads all_reports.json from a benchmark run and produces:
  - TQP_scorecard.csv    :  T1-T3 / Q1-Q4 / P1-P3 per model + weighted total
  - Q4_cross_version.csv :  same-building across IFC2x3/4/4.3 comparison
  - P3_cross_software.csv:  same-building across Archicad/Revit/Allplan comparison
  - summary.md           :  human-readable diagnosis — where are the bottlenecks
"""
import csv
import json
import sys
from pathlib import Path
from collections import defaultdict

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))


def load_reports(json_path: Path):
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    return data


# ---------- T/Q/P mapping ----------

def t1_robustness(r):
    """T1 解析鲁棒性 — 能不能跑完"""
    return r["axes"]["A"]["score"], r["axes"]["A"]["detail"]


def t2_extraction(r):
    """T2 实体覆盖度 — 提取器抓到了多少构件"""
    return r["axes"]["B"]["score"], r["axes"]["B"]["detail"]


def t3_field_coverage(r):
    """T3 字段完整度 — 审查时多少字段不为空"""
    return r["axes"]["C"]["score"], r["axes"]["C"]["detail"]


def q1_geometry_sanity(r):
    """Q1 几何合理性 — 尺寸在合理范围内"""
    return r["axes"]["D"]["score"], r["axes"]["D"]["detail"]


def q2_rule_activation(r):
    """Q2 规则激活率 — 相关规则有多少真的审到了东西"""
    return r["axes"]["E"]["score"], r["axes"]["E"]["detail"]


def q3_review_output(r):
    """Q3 审查产出率 — issue数量和not_checked比例"""
    issues = r.get("issues", 0)
    not_checked = r.get("not_checked", 0)
    total = issues + not_checked
    if total == 0:
        return 0.0, "no review output at all"
    # issue占比越高越好；但issue太多可能是误报，这里只算"有产出"
    issue_ratio = issues / total
    # 基础分：有任何审查产出就给60，issue比例加成
    score = 60.0 + 40.0 * issue_ratio
    return score, f"issues={issues} not_checked={not_checked} (ratio={issue_ratio:.0%})"


def q4_cross_version(reports):
    """Q4 跨版本一致性 — 同一建筑不同IFC版本的结果差异
    返回每组对比的差异分数
    """
    # 找 Building-Architecture 在 IFC2x3/IFC4/IFC4.3 三个版本
    groups = defaultdict(list)
    for r in reports:
        cat = r.get("category", "")
        fname = r["file"]
        if fname == "Building-Architecture.ifc":
            version = cat.split("/")[-1] if "/" in cat else cat
            groups["Building-Architecture"].append((version, r))
        if fname == "Building-Hvac.ifc":
            version = cat.split("/")[-1] if "/" in cat else cat
            groups["Building-Hvac"].append((version, r))
        if fname == "Building-Structural.ifc":
            version = cat.split("/")[-1] if "/" in cat else cat
            groups["Building-Structural"].append((version, r))
    return groups


def p1_performance(r):
    """P1 性能 — 解析速度"""
    return r["axes"]["F"]["score"], r["axes"]["F"]["detail"]


def p3_cross_software(reports):
    """P3 跨软件一致性 — Smiley-West 在 Archicad vs Allplan，FZK-Haus 在 Archicad vs ADT"""
    groups = defaultdict(list)
    for r in reports:
        fname = r["file"]
        if "Smiley-West" in fname:
            sw = "Archicad20" if "Archicad20" in fname else "Allplan"
            groups["Smiley-West-Office"].append((sw, r))
        if "FZK-Haus" in fname:
            sw = "Archicad11" if "Archicad11" in fname else "ADT"
            groups["FZK-Haus"].append((sw, r))
    return groups


# ---------- Weighted total ----------

T_WEIGHTS = {"T1": 0.10, "T2": 0.10, "T3": 0.10}
Q_WEIGHTS = {"Q1": 0.10, "Q2": 0.15, "Q3": 0.15, "Q4": 0.10}
P_WEIGHTS = {"P1": 0.10, "P3": 0.10}
# Note: Q4 and P3 are group-level metrics; per-model we use 90pt base


def grade(total):
    if total >= 90: return "S"
    if total >= 80: return "A"
    if total >= 65: return "B"
    if total >= 50: return "C"
    return "D"


def compute_tqp_per_model(r, q4_avg=None, p3_avg=None):
    """Compute T/Q/P score for one model.
    q4_avg/p3_avg: group-level bonus factor (0-100) applied only for models in those groups.
    """
    t1, _ = t1_robustness(r)
    t2, _ = t2_extraction(r)
    t3, _ = t3_field_coverage(r)
    q1, _ = q1_geometry_sanity(r)
    q2, _ = q2_rule_activation(r)
    q3, _ = q3_review_output(r)
    p1, _ = p1_performance(r)

    t_layer = (T_WEIGHTS["T1"] * t1 + T_WEIGHTS["T2"] * t2 + T_WEIGHTS["T3"] * t3) / sum(T_WEIGHTS.values())
    q_layer = (Q_WEIGHTS["Q1"] * q1 + Q_WEIGHTS["Q2"] * q2 + Q_WEIGHTS["Q3"] * q3) / (Q_WEIGHTS["Q1"]+Q_WEIGHTS["Q2"]+Q_WEIGHTS["Q3"])
    p_layer = p1  # P3 is group-level

    total = (t1*0.10 + t2*0.10 + t3*0.10 +
             q1*0.10 + q2*0.15 + q3*0.15 +
             p1*0.10)
    # if we have group-level Q4/P3, scale to full 100
    if q4_avg is not None and p3_avg is not None:
        total += q4_avg * 0.10 + p3_avg * 0.10
    elif q4_avg is not None:
        total += q4_avg * 0.10
        total /= 0.90  # normalize
    elif p3_avg is not None:
        total += p3_avg * 0.10
        total /= 0.90
    else:
        total /= 0.80  # no group-level metrics available

    return {
        "T1_robustness": round(t1, 1),
        "T2_extraction": round(t2, 1),
        "T3_field_cov": round(t3, 1),
        "T_layer_avg": round(t_layer, 1),
        "Q1_geom_sanity": round(q1, 1),
        "Q2_rule_activation": round(q2, 1),
        "Q3_review_output": round(q3, 1),
        "Q_layer_avg": round(q_layer, 1),
        "P1_performance": round(p1, 1),
        "P_layer_avg": round(p1, 1),
        "total_score": round(total, 1),
        "grade": grade(total),
    }


# ---------- Reports ----------

def write_tqp_csv(reports, outdir: Path):
    """Write per-model T/Q/P scorecard."""
    rows = []
    for r in reports:
        tqp = compute_tqp_per_model(r)
        row = {
            "category": r.get("category", ""),
            "file": r["file"],
            "schema": r.get("schema", ""),
            "size_mb": r.get("size_mb", 0),
            **tqp,
        }
        rows.append(row)

    cols = ["category", "file", "schema", "size_mb",
            "T1_robustness", "T2_extraction", "T3_field_cov", "T_layer_avg",
            "Q1_geom_sanity", "Q2_rule_activation", "Q3_review_output", "Q_layer_avg",
            "P1_performance", "P_layer_avg",
            "total_score", "grade"]

    csv_path = outdir / "TQP_scorecard.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"TQP scorecard: {csv_path}")
    return rows


def write_q4_comparison(reports, outdir: Path):
    """Q4 跨版本一致性对比"""
    groups = q4_cross_version(reports)
    csv_path = outdir / "Q4_cross_version.csv"
    rows = []
    for grp_name, members in groups.items():
        members.sort(key=lambda x: x[0])
        versions = [v for v, _ in members]
        # key metrics to compare
        metrics = ["score", "storeys", "rooms", "issues", "not_checked",
                   "parse_secs"]
        axis_names = ["A", "B", "C", "D", "E", "F"]
        metric_names = metrics + [f"{a}_score" for a in axis_names]

        row = {"model_group": grp_name, "versions_compared": ",".join(versions)}

        # compute variation across versions for each metric
        for m in metrics:
            vals = []
            for _, r in members:
                v = r.get(m)
                if isinstance(v, (int, float)):
                    vals.append(v)
            if len(vals) >= 2 and max(vals) > 0:
                spread = (max(vals) - min(vals)) / max(vals) * 100
                consistency = max(0, 100 - spread)
                row[f"{m}_consistency_%"] = round(consistency, 1)
                row[f"{m}_values"] = ",".join(f"{v}" for v in vals)
            else:
                row[f"{m}_consistency_%"] = ""
                row[f"{m}_values"] = ",".join(str(r.get(m, "")) for _, r in members)

        for a in axis_names:
            vals = []
            for _, r in members:
                v = r.get("axes", {}).get(a, {}).get("score", 0)
                vals.append(v)
            if max(vals) > 0:
                spread = (max(vals) - min(vals)) / max(vals) * 100
                consistency = max(0, 100 - spread)
                row[f"{a}_consistency_%"] = round(consistency, 1)
            else:
                row[f"{a}_consistency_%"] = 100.0

        # overall Q4 score: average of per-axis consistency
        ax_consistencies = [row.get(f"{a}_consistency_%", 0) for a in axis_names
                            if row.get(f"{a}_consistency_%") is not None
                            and row.get(f"{a}_consistency_%") != ""]
        if ax_consistencies:
            row["Q4_overall_consistency"] = round(sum(ax_consistencies)/len(ax_consistencies), 1)

        rows.append(row)

    if rows:
        cols = list(rows[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        print(f"Q4 cross-version comparison: {csv_path}")
    return rows


def write_p3_comparison(reports, outdir: Path):
    """P3 跨软件一致性对比"""
    groups = p3_cross_software(reports)
    csv_path = outdir / "P3_cross_software.csv"
    rows = []
    for grp_name, members in groups.items():
        members.sort(key=lambda x: x[0])
        softwares = [v for v, _ in members]

        row = {"model_group": grp_name, "softwares_compared": ",".join(softwares)}

        axis_names = ["A", "B", "C", "D", "E", "F"]
        metrics = ["score", "storeys", "rooms", "issues", "not_checked", "size_mb"]

        for m in metrics:
            vals = []
            for _, r in members:
                v = r.get(m)
                if isinstance(v, (int, float)):
                    vals.append(v)
            if len(vals) >= 2 and max(vals) > 0:
                spread = (max(vals) - min(vals)) / max(vals) * 100
                consistency = max(0, 100 - spread)
                row[f"{m}_consistency_%"] = round(consistency, 1)
                row[f"{m}_values"] = ",".join(f"{v:.1f}" if isinstance(v, float) else f"{v}" for v in vals)
            else:
                row[f"{m}_consistency_%"] = ""
                row[f"{m}_values"] = ",".join(str(r.get(m, "")) for _, r in members)

        for a in axis_names:
            vals = []
            for _, r in members:
                v = r.get("axes", {}).get(a, {}).get("score", 0)
                vals.append(v)
            if max(vals) > 0:
                spread = (max(vals) - min(vals)) / max(vals) * 100
                consistency = max(0, 100 - spread)
                row[f"{a}_consistency_%"] = round(consistency, 1)
            else:
                row[f"{a}_consistency_%"] = 100.0

        ax_consistencies = [row.get(f"{a}_consistency_%", 0) for a in axis_names
                            if row.get(f"{a}_consistency_%") is not None
                            and row.get(f"{a}_consistency_%") != ""]
        if ax_consistencies:
            row["P3_overall_consistency"] = round(sum(ax_consistencies)/len(ax_consistencies), 1)

        rows.append(row)

    if rows:
        cols = list(rows[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        print(f"P3 cross-software comparison: {csv_path}")
    return rows


def write_summary_md(reports, tqp_rows, q4_rows, p3_rows, outdir: Path):
    """Write a human-readable diagnosis markdown."""
    n = len(reports)
    avg_score = sum(r["score"] for r in reports) / n if n else 0

    # average T/Q/P layers
    t_avg = sum(row["T_layer_avg"] for row in tqp_rows) / len(tqp_rows)
    q_avg = sum(row["Q_layer_avg"] for row in tqp_rows) / len(tqp_rows)
    p_avg = sum(row["P_layer_avg"] for row in tqp_rows) / len(tqp_rows)

    # find the weakest layer
    layers = [("基础层 T", t_avg), ("质量层 Q", q_avg), ("实用层 P", p_avg)]
    weakest = min(layers, key=lambda x: x[1])
    strongest = max(layers, key=lambda x: x[1])

    # weakest individual dimension
    dims = [
        ("T1 解析鲁棒性", sum(r["T1_robustness"] for r in tqp_rows)/len(tqp_rows)),
        ("T2 实体覆盖度", sum(r["T2_extraction"] for r in tqp_rows)/len(tqp_rows)),
        ("T3 字段完整度", sum(r["T3_field_cov"] for r in tqp_rows)/len(tqp_rows)),
        ("Q1 几何合理性", sum(r["Q1_geom_sanity"] for r in tqp_rows)/len(tqp_rows)),
        ("Q2 规则激活率", sum(r["Q2_rule_activation"] for r in tqp_rows)/len(tqp_rows)),
        ("Q3 审查产出率", sum(r["Q3_review_output"] for r in tqp_rows)/len(tqp_rows)),
        ("P1 性能", sum(r["P1_performance"] for r in tqp_rows)/len(tqp_rows)),
    ]
    dims.sort(key=lambda x: x[1])

    md = []
    md.append("# ArchCheck 实用性测试报告")
    md.append("")
    md.append(f"测试模型数：**{n}** 个")
    md.append(f"原始 benchmark 平均分：**{avg_score:.1f}**")
    md.append("")
    md.append("## 三层得分总览")
    md.append("")
    md.append("| 层级 | 平均分 | 权重 | 状态 |")
    md.append("|------|--------|------|------|")
    for name, val in layers:
        flag = "🟢" if val >= 70 else ("🟡" if val >= 50 else "🔴")
        w = {"基础层 T": "30%", "质量层 Q": "50%", "实用层 P": "20%"}[name]
        md.append(f"| {name} | {val:.1f} | {w} | {flag} |")
    md.append("")
    md.append(f"**最薄弱层级：{weakest[0]}（{weakest[1]:.1f}分）**")
    md.append(f"**最强层级：{strongest[0]}（{strongest[1]:.1f}分）**")
    md.append("")
    md.append("## 各维度排行（从弱到强）")
    md.append("")
    for name, val in dims:
        bar = "█" * int(val/5) + "░" * (20 - int(val/5))
        md.append(f"- **{name}**：{val:.1f}  `{bar}`")
    md.append("")

    # Q4 section
    if q4_rows:
        md.append("## Q4 跨版本一致性对比")
        md.append("")
        md.append("| 模型组 | 对比版本 | 整体一致性 | 核心差异 |")
        md.append("|--------|---------|-----------|---------|")
        for row in q4_rows:
            grp = row["model_group"]
            vers = row["versions_compared"]
            overall = row.get("Q4_overall_consistency", "N/A")
            # find biggest difference
            diffs = []
            for k, v in row.items():
                if k.endswith("_consistency_%") and v not in ("", None):
                    dim = k.replace("_consistency_%", "")
                    diffs.append((dim, v))
            diffs.sort(key=lambda x: x[1])
            worst3 = "; ".join(f"{d}={v:.0f}%" for d, v in diffs[:3])
            md.append(f"| {grp} | {vers} | {overall} | {worst3} |")
        md.append("")

    # P3 section
    if p3_rows:
        md.append("## P3 跨软件一致性对比")
        md.append("")
        md.append("| 模型组 | 对比软件 | 整体一致性 | 核心差异 |")
        md.append("|--------|---------|-----------|---------|")
        for row in p3_rows:
            grp = row["model_group"]
            sws = row["softwares_compared"]
            overall = row.get("P3_overall_consistency", "N/A")
            diffs = []
            for k, v in row.items():
                if k.endswith("_consistency_%") and v not in ("", None):
                    dim = k.replace("_consistency_%", "")
                    diffs.append((dim, v))
            diffs.sort(key=lambda x: x[1])
            worst3 = "; ".join(f"{d}={v:.0f}%" for d, v in diffs[:3])
            md.append(f"| {grp} | {sws} | {overall} | {worst3} |")
        md.append("")

    # Diagnosis
    md.append("## 诊断与改进建议")
    md.append("")
    md.append("### 主要矛盾")
    md.append("")
    # figure out what to say
    if weakest[0] == "基础层 T":
        md.append("- 基础解析层是最大瓶颈，说明提取器漏构件/字段问题严重")
        md.append("- 优先级最高：补全实体类型映射、字段取值逻辑")
    elif weakest[0] == "质量层 Q":
        md.append("- 审查质量层是最大瓶颈，说明规则跑起来了但产出质量不高")
        md.append("- 优先级最高：提升规则激活率、减少 not_checked 跳过项")
    else:
        md.append("- 性能层是最大瓶颈，说明大模型跑太慢")
        md.append("- 优先级最高：优化解析性能、加缓存、并行处理")

    md.append("")
    md.append("### Top 3 最弱维度的改进方向")
    md.append("")
    for name, val in dims[:3]:
        suggestion = {
            "T2 实体覆盖度": "检查 extractor 中缺失的实体类型映射（特别是 IFC4/4.3 新类型）",
            "T3 字段完整度": "增加字段回退逻辑：优先 Qto → 其次几何计算 → 最后用类型属性估算",
            "Q2 规则激活率": "梳理规则前置条件，降低规则触发门槛，增加兜底判断路径",
            "Q3 审查产出率": "排查 not_checked 的根因：是缺数据还是规则条件太严",
            "Q1 几何合理性": "检查坐标系统和单位转换，确保提取的尺寸是米制",
            "P1 性能": "优化 bbox 缓存、减少重复几何计算、考虑并行解析",
            "T1 解析鲁棒性": "增加异常捕获的粒度，单个构件失败不影响整体流程",
        }.get(name, "需要进一步分析根因")
        md.append(f"- **{name}（{val:.1f}分）**：{suggestion}")

    md.append("")
    md.append("## 逐模型得分表")
    md.append("")
    md.append("| 分类 | 文件 | 大小 | T层 | Q层 | P层 | 总分 | 等级 |")
    md.append("|------|------|------|-----|-----|-----|------|------|")
    for row in sorted(tqp_rows, key=lambda x: x["total_score"], reverse=True):
        md.append(f"| {row['category']} | {row['file'][:30]} | {row['size_mb']:.1f}MB | "
                  f"{row['T_layer_avg']:.0f} | {row['Q_layer_avg']:.0f} | "
                  f"{row['P_layer_avg']:.0f} | {row['total_score']:.1f} | {row['grade']} |")

    out_path = outdir / "summary.md"
    out_path.write_text("\n".join(md), encoding="utf-8")
    print(f"Summary report: {out_path}")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("input_json", help="all_reports.json from run_full_benchmark")
    ap.add_argument("--out", default="output/benchmark_0908")
    args = ap.parse_args()

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    reports = load_reports(args.input_json)
    print(f"Loaded {len(reports)} reports")

    tqp_rows = write_tqp_csv(reports, outdir)
    q4_rows = write_q4_comparison(reports, outdir)
    p3_rows = write_p3_comparison(reports, outdir)
    write_summary_md(reports, tqp_rows, q4_rows, p3_rows, outdir)

    print("\nDone.")


if __name__ == "__main__":
    main()
