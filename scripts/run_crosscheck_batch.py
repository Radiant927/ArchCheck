"""批量 crosscheck —— 对一批 IFC 模型逐个互检，聚合逐模型对错总表。

排除：打不开/超大/基础设施类（无楼层）模型。
Usage: python scripts/run_crosscheck_batch.py [--out output/crosscheck_v3]
"""
import argparse
import sys
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
            rows_summary.append({
                "model": model, "total": total, "ok": ok, "wrong": wrong,
                "miss": miss, "extra": extra,
                "acc": f"{acc:.1f}%" if acc is not None else "—",
                "cats": ",".join(sorted(stats.keys())),
            })
            # 明细落盘
            CC.write_outputs(model, rows, stats, out)
        except Exception as e:
            rows_summary.append({"model": rel, "total": 0, "ok": 0, "wrong": 0,
                                 "miss": 0, "extra": 0, "acc": f"FAIL {e}", "cats": ""})

    # 聚合总表
    lines = ["# crosscheck 批量互检总表", "", "| 模型 | 真值构件 | ✓字段 | ✗ | 漏读 | 多读 | 字段正确率 | 类别 |",
             "|---|---:|---:|---:|---:|---:|---|---|"]
    for r in rows_summary:
        lines.append(f"| {r['model']} | {r['total']} | {r['ok']} | {r['wrong']} "
                     f"| {r['miss']} | {r['extra']} | {r['acc']} | {r['cats']} |")
    (out / "_batch_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\nWrote", out / "_batch_summary.md")


if __name__ == "__main__":
    main()
