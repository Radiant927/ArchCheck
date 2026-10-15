"""批量 crosscheck —— 对一批 IFC 模型逐个互检，聚合逐模型对错总表。

排除：打不开/超大/基础设施类（无楼层）模型。
Usage: python scripts/run_crosscheck_batch.py [--out output/crosscheck_v3]
"""
import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "scripts"))

import crosscheck_ifc as CC                          # noqa: E402

# (文件名前缀, 相对 bim/test-suites 路径)
MODELS = [
    "official/IFC2x3/Building-Architecture.ifc",
    "official/IFC2x3/Building-Structural.ifc",
    "official/IFC2x3/Building-Hvac.ifc",
    "official/IFC4/Building-Architecture.ifc",
    "official/IFC4/Building-Structural.ifc",
    "official/IFC4/Building-Hvac.ifc",
    "official/IFC4.3/Building-Architecture.ifc",
    "official/IFC4.3/Building-Structural.ifc",
    "official/IFC4.3/Building-Hvac.ifc",
    "official/ReferenceView/wall-with-opening-and-window.ifc",
    "real-project/FZK-Haus_Archicad11_IFC2x3.ifc",
    "real-project/Jasmin-Sun-Residence_Archicad9_IFC2x3.ifc",
    "real-project/Institute-Building_Archicad11_IFC2x3.ifc",
    "real-project/Basic-Sample-Project_Revit_IFC4.ifc",
    "real-project/Building-4351_IFC2x3.ifc",
    "mep/hvac/Revit-MEP-Sample_IFC4.ifc",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="output/crosscheck_v3")
    ap.add_argument("--root", default="bim/test-suites")
    args = ap.parse_args()

    root = Path(args.root)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    rows_summary = []
    all_rows = []
    for rel in MODELS:
        p = root / rel
        print(f"== {rel}")
        try:
            model, rows, stats, _ = CC.crosscheck_file(p)
            ok = sum(s["ok"] for s in stats.values())
            wrong = sum(s["wrong"] for s in stats.values())
            miss = sum(s["missing_ext"] for s in stats.values())
            extra = sum(s["extra_ext"] for s in stats.values())
            total = sum(s["total"] for s in stats.values())
            checked = ok + wrong
            acc = (ok / checked * 100) if checked else None
            # 按维度拆分
            dims = defaultdict(lambda: {"ok": 0, "wrong": 0, "total": 0})
            for r in rows:
                d = r.get("dimension", "几何尺寸")
                dims[d]["total"] += 1
                if r["verdict"] == "✓":
                    dims[d]["ok"] += 1
                elif r["verdict"] == "✗":
                    dims[d]["wrong"] += 1
            for d, v in dims.items():
                v["acc"] = (v["ok"] / (v["ok"] + v["wrong"]) * 100
                           ) if (v["ok"] + v["wrong"]) else None
            rows_summary.append({
                "model": model, "total": total, "ok": ok, "wrong": wrong,
                "miss": miss, "extra": extra,
                "acc": f"{acc:.1f}%" if acc is not None else "—",
                "cats": ",".join(sorted(stats.keys())),
                "dims": dict(dims),
            })
            all_rows.extend(rows)
            # 明细落盘
            CC.write_outputs(model, rows, stats, out)
        except Exception as e:
            rows_summary.append({"model": rel, "total": 0, "ok": 0, "wrong": 0,
                                 "miss": 0, "extra": 0, "acc": f"FAIL {e}",
                                 "cats": "", "dims": {}})

    # 全局按维度汇总
    dim_global = defaultdict(lambda: {"ok": 0, "wrong": 0, "total": 0})
    for r in all_rows:
        d = r.get("dimension", "几何尺寸")
        dim_global[d]["total"] += 1
        if r["verdict"] == "✓":
            dim_global[d]["ok"] += 1
        elif r["verdict"] == "✗":
            dim_global[d]["wrong"] += 1

    # 聚合总表
    lines = ["# crosscheck 批量互检总表（v5 · 5 维度）", "",
             "> 维度：计数 / 存在性 / 几何尺寸 / 分类 / 属性。"
             "「分类」维度的真值侧靠关键词启发式推断，仅供参考，不计入主正确率。",
             "",
             "## 一、总表", "",
             "| 模型 | 真值构件 | ✓字段 | ✗ | 漏读 | 多读 | 字段正确率 | 类别 |",
             "|---|---:|---:|---:|---:|---:|---|---|"]
    for r in rows_summary:
        lines.append(f"| {r['model']} | {r['total']} | {r['ok']} | {r['wrong']} "
                     f"| {r['miss']} | {r['extra']} | {r['acc']} | {r['cats']} |")

    # 按维度拆分总表（只算有判定的行，不含漏/多/漏字段）
    lines += ["", "", "## 二、按维度拆分", ""]
    dim_list = ["计数", "存在性", "几何尺寸", "分类", "属性"]
    header = "| 模型 | " + " | ".join(f"{d} 正确率" for d in dim_list) + " |"
    sep = "|---|" + "|".join("---:|" for d in dim_list)
    lines += [header, sep]
    for r in rows_summary:
        row = [r["model"]]
        for d in dim_list:
            v = r["dims"].get(d, {})
            acc = v.get("acc")
            row.append(f"{acc:.1f}%" if acc is not None else "—")
        lines.append("| " + " | ".join(row) + " |")

    # 全局维度汇总
    lines += ["", "", "## 三、全局维度汇总（所有模型合计）", ""]
    lines.append("| 维度 | 总行数 | ✓ | ✗ | 正确率 | 说明 |")
    lines.append("|---|---:|---:|---:|---:|---|")
    dim_notes = {
        "计数": "每类构件的 IFC by_type 真值 vs 提取器计数",
        "存在性": "逐构件有无 — 漏读 / 多读",
        "几何尺寸": "厚度/长度/高度/宽度/截面等几何量（v4 已有维度）",
        "分类": "room_type / pipe_type 等分类标签（真值侧启发式，**仅供参考**）",
        "属性": "Pset/Qto 标量值 vs 提取器对应字段",
    }
    for d in dim_list:
        v = dim_global.get(d, {})
        total = v.get("total", 0)
        ok = v.get("ok", 0); wrong = v.get("wrong", 0)
        acc = f"{ok / (ok + wrong) * 100:.1f}%" if (ok + wrong) else "—"
        lines.append(f"| {d} | {total} | {ok} | {wrong} | {acc} | {dim_notes.get(d, '')} |")

    lines += ["", "",
              "## 四、关于「分类」维度的说明", "",
              "分类维度的真值侧用和提取器相同的关键词启发式（room 用 `_classify_room_type`、"
              "pipe 用名称关键词），两边用同一套逻辑——但因为真值侧信息更少（只有名字，没有 LongName / 系统名），"
              "所以**分类维度的错误率不代表提取器错**，更多反映的是「命名信息不足以可靠分类」。",
              "该维度的价值在于：标记出「哪些构件的分类是靠名字猜的、哪些有明确属性」。",
              ""]

    (out / "_batch_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\nWrote", out / "_batch_summary.md")


if __name__ == "__main__":
    main()
