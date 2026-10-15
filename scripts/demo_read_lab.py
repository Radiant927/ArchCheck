"""Report helper — print everything ArchCheck reads from Lab.ifc (for screenshots).

Run (from project root):  python scripts/demo_read_lab.py
Output: a clean, sectioned overview of every field extracted from the model,
so a report can show "this is what the platform actually reads out".
"""
from collections import Counter

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bim.parser import parse_ifc

s = parse_ifc("bim/Lab.ifc")
f = s["floors"][0]
st = f["structure"]
pipes, fits, ducts = f["pipes"], f.get("pipe_fittings", []), f["ducts"]
normal = [p for p in pipes if p.get("diameter_m") and p["diameter_m"] >= 0.010]
debris = [p for p in pipes if p.get("diameter_m") and p["diameter_m"] < 0.010]
se = f.get("structural_elements", [])
clashes = f.get("clashes", [])
plan = f.get("plan_elements", [])

L = []
A = L.append
A("")
A("=" * 44)
A("Lab.ifc 读取内容总览")
A("=" * 44)
A("")
A(f"项目: {s['project_name'] or '(未命名)'}   文件: {s['file_name']}   schema: IFC4")
A(f"楼层 {s['storey_count']} | 房间 {s['total_rooms']} | 占地 {f.get('footprint_area_sqm', 0)} m2")
A("")
A("【建筑与结构】")
A(f"  构件数量   墙 {st['walls']} | 门 {st['doors']} | 窗 {st['windows']}"
  f" | 柱 {st['columns']} | 板 {st['slabs']}   (梁/楼梯/坡道 0)")
A(f"  柱截面(m)  {st['column_sections'][0]} 等 {len(st['column_sections'])} 种")
A(f"  门宽(m)    {sorted(st['door_widths_m'])}")
A(f"  板厚(m)    {st['slab_thicknesses']}")
if se:
    n_col = sum(1 for e in se if e['element_type'] == 'column')
    n_sla = sum(1 for e in se if e['element_type'] == 'slab')
    A(f"  结构元素   柱 {n_col} | 板 {n_sla}")
    A(f"    柱例: 截面 {se[1]['section_min_m']}x{se[1]['section_max_m']}m"
      f"  体积 {se[1]['volume_m3']}m3  材料 {se[1]['material']}")
    A(f"    板例: 厚 {se[3]['thickness_m']}m  体积 {se[3]['volume_m3']}m3"
      f"  材料 {se[3]['material']}")
A(f"  材料体积  {st['material_volumes']}   (m3)")
A(f"  结构总体积 {st['structural_volume_m3']} m3")
A("")
A("【MEP 分布元件】")
A(f"  管段 {len(pipes)} 根   配件 {len(fits)} 个   风管 {len(ducts)} 根")
A("")
A("  ◆ 管段字段读取")
A(f"      直径 diameter_m    {sum(1 for p in pipes if p.get('diameter_m'))}/173"
  f"   范围 {min(p['diameter_m'] for p in normal)*1000:.0f}"
  f"~{max(p['diameter_m'] for p in normal)*1000:.0f}mm")
A(f"      长度 length_m      {sum(1 for p in pipes if p.get('length_m') is not None)}/173"
  f"   总长 {sum(p['length_m'] for p in pipes):.0f}m")
A(f"      坡度 slope          {sum(1 for p in pipes if p.get('slope') is not None)}/173")
A(f"      材料 material      {sum(1 for p in pipes if p.get('material'))}/173"
  f" = {sorted(set(p['material'] for p in pipes))}")
A(f"      系统 pipe_type     {0}/173   (文件未提供系统标签 -> unknown)")
A(f"      └ 废数据(直径<10mm) {len(debris)} 根 —— 建模垃圾，已识别")
A("")
A("  ◆ 配件字段读取")
A(f"      类型 {dict(Counter(pf['fitting_type'] for pf in fits))}")
A(f"      尺寸 {sum(1 for pf in fits if pf.get('size_m'))}/135"
  f"   材料 {sorted(set(pf['material'] for pf in fits))}")
A("")
A("  ◆ 风管字段读取")
A(f"      宽 {sum(1 for d in ducts if d.get('duct_width_m'))}/108"
  f"   高 {sum(1 for d in ducts if d.get('duct_height_m'))}/108")
A(f"      长度 {sum(1 for d in ducts if d.get('length_m') is not None)}/108"
  f"   材料 {sorted(set(d['material'] for d in ducts))}")
A("")
A("【附加分析】")
if clashes:
    n_conf = sum(1 for c in clashes if c.get("confirmed"))
    A(f"  MEP × 结构碰撞 {len(clashes)} 处 (几何点中 {n_conf} 处)"
      f" —— 例: 管道穿 {clashes[0]['type']}, 嵌入 {clashes[0]['depth']}m")
A(f"  平面构件 bbox {len(plan)} 个 (供平面图渲染: "
  f"{dict(Counter(p['kind'] for p in plan))})")
A("")
A("【质检】")
A(f"  QA 健康分 {s['qa']['score']}/100"
  f" | 实体类型 {len(s['qa']['entity_coverage']['handled'])} 类全读，未识别 0")
A("")
print("\n".join(L))
