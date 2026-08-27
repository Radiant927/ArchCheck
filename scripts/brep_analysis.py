#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B-Rep 调研 + IFC 组件统计（8-26 会议任务 1）。

对每个样例 IFC：
  1. B-Rep 相关实体数量（IfcFacetedBrep / IfcAdvancedBrep / IfcManifoldSolidBrep /
     IfcClosedShell / IfcFaceBasedSurfaceModel / IfcShellBasedSurfaceModel /
     IfcBooleanClippingResult ...）
  2. 按元素统计几何表示类型分布（拉伸 / 旋转 / 扫掠 / B-Rep / 网格 / bbox / 布尔）
  3. 组件类型分布（柱/梁/板/墙/门/窗/管道/风管/电气设备...）

产出 markdown 报告，用于判断：主流样例里 B-Rep 占比多少，台阶③精确几何
是否可以依赖 B-Rep 直接查询，CSG 布尔运算是否仍必要。

用法: python scripts/brep_analysis.py [--out presentation/2026-08-26/B-Rep调研与组件统计_2026-08-27.md]
"""
import argparse
import collections
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ifcopenshell  # noqa: E402

SAMPLES = [
    ("FZK_Haus", "bim/samples/FZK_Haus.ifc"),
    ("office_3f", "bim/samples/office_3f.ifc"),
    ("Duplex_MEP", "bim/samples/Duplex_MEP_20110907.ifc"),
    ("Schependomlaan", "bim/samples/Schependomlaan.ifc"),
]

# B-Rep / 布尔 / 网格 相关实体（直接计数 by_type）
BREP_ENTITIES = [
    "IfcFacetedBrep", "IfcAdvancedBrep", "IfcManifoldSolidBrep",
    "IfcClosedShell", "IfcOpenShell", "IfcFaceBasedSurfaceModel",
    "IfcShellBasedSurfaceModel", "IfcBooleanClippingResult", "IfcBooleanResult",
    "IfcTriangulatedFaceSet", "IfcPolygonalFaceSet",
]

# 表示项类型 -> 类别（几何内核分类）
REPR_KIND = {
    "IfcExtrudedAreaSolid": "拉伸 (Extruded)",
    "IfcRevolvedAreaSolid": "旋转 (Revolved)",
    "IfcSweptDiskSolid": "扫掠 (SweptDisk)",
    "IfcFacetedBrep": "B-Rep",
    "IfcAdvancedBrep": "B-Rep",
    "IfcManifoldSolidBrep": "B-Rep",
    "IfcFaceBasedSurfaceModel": "B-Rep",
    "IfcShellBasedSurfaceModel": "B-Rep",
    "IfcBooleanResult": "布尔 (Boolean)",
    "IfcBooleanClippingResult": "布尔 (Boolean)",
    "IfcCsgSolid": "CSG",
    "IfcBoundingBox": "bbox",
    "IfcTriangulatedFaceSet": "网格 (Mesh)",
    "IfcPolygonalFaceSet": "网格 (Mesh)",
    "IfcPolyline": "线 (Polyline)",
}

# IFC 实体类型 -> 构件类别（组件统计）
COMPONENT_KIND = {
    "IfcColumn": "柱", "IfcColumnStandardCase": "柱",
    "IfcBeam": "梁", "IfcBeamStandardCase": "梁",
    "IfcSlab": "板", "IfcSlabStandardCase": "板",
    "IfcWall": "墙", "IfcWallStandardCase": "墙", "IfcWallElementedCase": "墙",
    "IfcDoor": "门", "IfcWindow": "窗",
    "IfcStair": "楼梯", "IfcStairFlight": "楼梯", "IfcRamp": "坡道", "IfcRampFlight": "坡道",
    "IfcPipeSegment": "管道", "IfcPipeFitting": "管道(配件)",
    "IfcDuctSegment": "风管", "IfcDuctFitting": "风管(配件)",
    "IfcFlowSegment": "流段(管/风管通用)",
    "IfcFlowTerminal": "末端设备", "IfcFlowController": "控制设备",
    "IfcFlowFixture": "卫生洁具", "IfcSanitaryTerminal": "卫生洁具",
    "IfcLightFixture": "灯具", "IfcElectricAppliance": "电气设备",
    "IfcElectricDistributionBoard": "配电箱",
    "IfcSpace": "空间", "IfcBuildingStorey": "楼层",
}


def _count(m, type_name):
    """len(m.by_type(...)) that tolerates entity types absent from the schema
    (e.g. IfcFlowFixture does not exist in IFC4)."""
    try:
        return len(m.by_type(type_name))
    except RuntimeError:
        return 0


def analyze(path):
    m = ifcopenshell.open(str(path))
    out = {"file": Path(path).name, "schema": m.schema}

    brep = collections.Counter()
    for t in BREP_ENTITIES:
        n = _count(m, t)
        if n:
            brep[t] = n
    out["brep_entities"] = dict(brep)

    repr_counter = collections.Counter()
    n_products_with_rep = 0
    for prod in m.by_type("IfcProduct"):
        rep = getattr(prod, "Representation", None)
        if rep is None:
            continue
        n_products_with_rep += 1
        for r in rep.Representations or []:
            for item in r.Items or []:
                cls = item.is_a()
                repr_counter[REPR_KIND.get(cls, "其他:" + cls)] += 1
    out["n_products_with_rep"] = n_products_with_rep
    out["n_products_total"] = len(m.by_type("IfcProduct"))
    out["representation"] = dict(repr_counter)

    comp = collections.Counter()
    for t, label in COMPONENT_KIND.items():
        n = _count(m, t)
        if n:
            comp[label] += n
    out["components"] = dict(comp)
    return out


def fmt_md(results):
    lines = []
    lines.append("# B-Rep 调研 + IFC 组件统计")
    lines.append("")
    lines.append("> 归属：presentation/2026-08-26/ · 生成日期 2026-08-27 · 脚本 `scripts/brep_analysis.py`")
    lines.append("> 目的：判断主流 IFC 样例中 B-Rep 占比，评估台阶③精确几何是否可依赖 B-Rep、CSG 是否仍必要")
    lines.append("")

    # B-Rep 实体表
    lines.append("## 一、B-Rep 相关实体计数（by_type）")
    lines.append("")
    all_brep_keys = sorted({k for r in results for k in r["brep_entities"]})
    lines.append("| 实体 | " + " | ".join(r["file"] for r in results) + " |")
    lines.append("|---|" + "---|" * len(results))
    for t in all_brep_keys:
        row = [t]
        for r in results:
            row.append(str(r["brep_entities"].get(t, 0)))
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # 表示类型分布表
    lines.append("## 二、几何表示类型分布（按表示项计数）")
    lines.append("")
    all_kinds = sorted({k for r in results for k in r["representation"]})
    lines.append("| 表示类型 | " + " | ".join(r["file"] for r in results) + " |")
    lines.append("|---|" + "---|" * len(results))
    for k in all_kinds:
        row = [k]
        for r in results:
            row.append(str(r["representation"].get(k, 0)))
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # 组件分布表
    lines.append("## 三、组件类型分布")
    lines.append("")
    all_comp = sorted({k for r in results for k in r["components"]})
    lines.append("| 组件 | " + " | ".join(r["file"] for r in results) + " |")
    lines.append("|---|" + "---|" * len(results))
    for k in all_comp:
        row = [k]
        for r in results:
            row.append(str(r["components"].get(k, 0)))
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # 结论
    lines.append("## 四、结论（模板，需按表格数字核对）")
    lines.append("")
    lines.append("- **B-Rep 占比**：从表一/表二看，主流样例以拉伸体为主，B-Rep 实体很少见 → 依赖 B-Rep 直接查询的收益有限。")
    lines.append("- **布尔运算**：`IfcBooleanClippingResult` 存在与否决定洞口/级联布尔差是否可读；表一给出计数。")
    lines.append("- **CSG 是否仍必要**：若主流样例为拉伸体且带布尔差，精确体积/洞口仍需 CSG 内核；若大量为网格/无精确实体，则先做网格体积而非 CSG。")
    lines.append("")
    return "\n".join(lines)


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "presentation" / "2026-08-26"
                                          / "B-Rep调研与组件统计_2026-08-27.md"))
    args = ap.parse_args()

    results = []
    for name, rel in SAMPLES:
        p = ROOT / rel
        print(f"analyzing {name} ...", flush=True)
        results.append(analyze(p))
        for r in results[-1]["representation"].items():
            print(f"    {r[0]}: {r[1]}")

    out = fmt_md(results)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(out, encoding="utf-8")
    print(f"\n报告已写入: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
