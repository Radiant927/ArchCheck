"""IFC crosscheck — 逐构件比对"文件直读真值 vs 提取器输出"，输出互检清单。

对每行 (GlobalId, 类别, 字段) 判定 ✓ / ✗ / 漏 / 多 + 根因标签。
用途：A2 阶段"哪对哪错"证据；A5 viewer 标注的数据源。

Usage:
    python scripts/crosscheck_ifc.py <ifc|dir> [--out output/crosscheck]
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom as ifcgeom

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from bim import extractor as EX                  # noqa: E402
from bim.parser import parse_ifc                  # noqa: E402

_GEOM_SETTINGS = ifcgeom.settings()

# 比对容差（米）：浮点误差内都算对
ABS_TOL_M = 0.02
REL_TOL = 0.02

# IFC 主类型 → 互检分类标签
# 注意：只列基类型。by_type 已含子类（IfcWall 覆盖 IfcWallStandardCase），
# 并列两者会让同一构件被真值侧双算。
TYPE_MAP = {
    "IfcWall": "wall",
    "IfcDoor": "door",
    "IfcWindow": "window",
    "IfcColumn": "column",
    "IfcBeam": "beam",
    "IfcSlab": "slab",
    "IfcFooting": "footing",
    "IfcStair": "stair",
    "IfcRailing": "railing",
    "IfcRamp": "ramp",
    "IfcPipeSegment": "pipe",
    "IfcPipeFitting": "pipe_fitting",
    "IfcDuctSegment": "duct",
    "IfcSanitaryTerminal": "sanitary",
    "IfcAirTerminal": "air_terminal",
    "IfcOutlet": "outlet",
    "IfcSpace": "room",
}

# 提取器只汇总计数（不逐件输出）的类别 → 其 structure 计数键。
# crosscheck 对这类走"计数比对"，避免误报逐件漏读。
COUNT_KEYS = {
    "stair": "stairs",
    "ramp": "ramps",
    "air_terminal": "air_terminals",
    "sanitary": "sanitary_fixtures",
    "outlet": "outlets",
    "pipe_fitting": "pipe_fittings",
}

# 真值侧需要 create_shape/bbox 的类别（几何构件：尺寸真值 + 中心匹配）。
# MEP 类（pipe/duct/末端）靠 id/计数/属性真值，逐件 tessellate 太慢。
GEOM_BBOX_CATS = {"wall", "door", "window", "column", "beam", "slab",
                  "footing", "railing", "stair", "ramp", "room"}

# 单位检测用的典型构件量级（米）
WALL_THICKNESS_RANGE = (0.08, 0.6)


def _close(a, b):
    if a is None or b is None:
        return False
    if abs(a - b) <= ABS_TOL_M:
        return True
    denom = max(abs(a), abs(b), 1e-6)
    return abs(a - b) / denom <= REL_TOL


def _bbox_dims(bbox):
    """从 6 元 bbox (x0,y0,x1,y1,z0,z1) 算 (dx, dy, dz)。"""
    x0, y0, x1, y1, z0, z1 = bbox
    return abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)


def _length_thickness_height_from_bbox(bbox, kind):
    """对墙/柱/梁/板：从 bbox 推 (length_m, thickness_m, height_m/深_m)。"""
    dx, dy, dz = _bbox_dims(bbox)
    if kind == "wall":
        h = dz
        t = min(dx, dy)
        l = max(dx, dy)
        return {"length_m": l, "thickness_m": t, "height_m": h}
    if kind in ("column", "beam"):
        h = dz if kind == "column" else max(dx, dy)
        section = [dx, dy, dz]
        section.remove(h)
        sec_min, sec_max = sorted(section)
        return {"height_m" if kind == "column" else "span_m": h,
                "section_min_m": sec_min, "section_max_m": sec_max}
    if kind == "slab":
        t = dz
        l = max(dx, dy)
        w = min(dx, dy)
        return {"thickness_m": t, "length_m": l, "width_m": w}
    return {}


# -------------------- IFC 直读真值 --------------------

def _ifc_bbox(elem):
    """从 IfcBoundingBox 或 Body 几何算 bbox，统一 (x0,y0,x1,y1,z0,z1) 格式。
    返回局部坐标下的 bbox，单位与模型一致。"""
    # 优先用 IfcBoundingBox（快）
    if elem.Representation:
        for rep in elem.Representation.Representations:
            if rep.RepresentationType == "BoundingBox":
                for item in rep.Items:
                    if item.is_a("IfcBoundingBox"):
                        c = item.Corner.Coordinates
                        dx, dy, dz = item.XDim, item.YDim, item.ZDim
                        return (c[0], c[1], c[0]+dx, c[1]+dy, c[2], c[2]+dz)
    # 退而求其次：用 ifcopenshell 几何工具（世界坐标，和提取侧 plan bbox 同一参照系）
    try:
        settings = ifcgeom.settings()
        # 必须输出世界坐标，否则空名构件靠几何中心匹配会失败（真值局部 vs 提取世界）
        settings.set(settings.USE_WORLD_COORDS, True)
        settings.set(settings.DISABLE_OPENING_SUBTRACTIONS, False)
        shape = ifcgeom.create_shape(settings, elem)
        verts = shape.geometry.verts
        xs, ys, zs = verts[0::3], verts[1::3], verts[2::3]
        return (min(xs), min(ys), max(xs), max(ys), min(zs), max(zs))
    except Exception:
        return None


def read_ifc_truth(ifc_path, world_scale=None):
    """直读 IFC 真值：每个构件的 GlobalId / 类别 / 名称 / bbox（世界坐标，原单位）/ 属性。
    返回 dict: {category: [{global_id, name, bbox_local, props}]}

    ``world_scale`` = metres-per-model-unit，应传 parser 校准后的
    scale_info.world_scale。混合单位模型（声明 mm 但几何实为 m，如
    Schependomlaan / Building-Structural）只读声明单位会错 1000 倍，所以
    由调用方传入校准值；为 None 时才退化为按声明单位探测。
    """
    m = ifcopenshell.open(str(ifc_path))
    out = defaultdict(list)

    # 声明单位探测（仅在 world_scale 未提供时使用）
    declared_scale = None
    for u in m.by_type("IfcUnitAssignment"):
        for ue in u.Units:
            if ue.is_a("IfcSIUnit") and ue.UnitType == "LENGTHUNIT":
                prefix = (ue.Prefix or "") if hasattr(ue, "Prefix") else ""
                declared_scale = {"": 1.0, "MILLI": 0.001, "CENTI": 0.01,
                                  "KILO": 1000.0}.get(prefix, 1.0)
    if declared_scale is None:
        # 非 SI 长度单位（英制 FOOT/INCH 等）：交给 ifcopenshell 解析换算系数
        try:
            import ifcopenshell.util.unit as _uu
            declared_scale = _uu.calculate_unit_scale(m)
        except Exception:
            declared_scale = 1.0
    if world_scale is None:
        world_scale = declared_scale

    for ifc_type, cat in TYPE_MAP.items():
        try:
            elems = m.by_type(ifc_type)
        except Exception:
            continue
        for elem in elems:
            # 几何类需要 bbox（尺寸真值 + 中心匹配）；MEP 类走 id/计数/属性真值，
            # 逐件 tessellate 太慢（如 Revit-MEP 800+ 管）。
            bbox = None
            if cat in GEOM_BBOX_CATS:
                try:
                    bbox = _ifc_bbox(elem)
                except Exception:
                    pass
            props = {}
            if hasattr(elem, "OverallWidth") and elem.OverallWidth is not None:
                props["overall_width"] = elem.OverallWidth
            if hasattr(elem, "OverallHeight") and elem.OverallHeight is not None:
                props["overall_height"] = elem.OverallHeight
            if hasattr(elem, "NominalDiameter") and elem.NominalDiameter is not None:
                props["nominal_diameter"] = elem.NominalDiameter
            # slab 厚度（米）：Qto/extrusion 用声明单位，PCA/bbox 用世界单位
            if cat == "slab":
                t = _truth_slab_thickness(elem, world_scale, declared_scale)
                if t is not None:
                    props["truth_thickness_m"] = t
            # beam/column 真实棱柱尺寸（拉伸截面 → PCA → 兜底），斜杆件用 bbox 会错
            elif cat in ("beam", "column"):
                info = EX._extrusion_profile_info(elem, 1.0)  # 模型单位
                prism = None
                if info:
                    prism = (info["section_min_m"], info["section_max_m"],
                             info["length_m"])
                else:
                    pca = EX._pca_dims(elem, _GEOM_SETTINGS, 1.0)  # (small, mid, big)
                    if pca:
                        prism = pca
                if prism:
                    props["prism_min_raw"] = prism[0]
                    props["prism_mid_raw"] = prism[1]
                    props["prism_big_raw"] = prism[2]
            # room 面积真值：从任一 IfcElementQuantity 的 GrossFloorArea/NetFloorArea
            elif cat == "room":
                for rel in (elem.IsDefinedBy or []):
                    if not rel.is_a("IfcRelDefinesByProperties"):
                        continue
                    pd = rel.RelatingPropertyDefinition
                    if not pd.is_a("IfcElementQuantity"):
                        continue
                    for q in pd.Quantities:
                        if q.Name in ("GrossFloorArea", "NetFloorArea") \
                                and q.is_a("IfcQuantityArea") and q.AreaValue > 0:
                            props["truth_area_raw"] = q.AreaValue
                            break
            out[cat].append({
                "global_id": elem.GlobalId,
                "name": elem.Name or "",
                "ifc_type": ifc_type,
                "bbox_local": bbox,
                "props": props,
            })

    return dict(out), world_scale


# -------------------- 真值侧的字段取值（独立于提取器的实现） --------------------

def _truth_slab_thickness(elem, world_scale, declared_scale):
    """真值侧板厚（米）。Qto/Extrusion 用模型声明单位（如 mm-declared Revit 的
    Qto 是 mm），PCA/bbox 用世界几何单位。返回米，或 None。
    """
    # 1. Qto（声明单位）
    for rel in (elem.IsDefinedBy or []):
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        pd = rel.RelatingPropertyDefinition
        if not pd.is_a("IfcElementQuantity") or pd.Name != "Qto_SlabBaseQuantities":
            continue
        for q in pd.Quantities:
            if q.Name == "GrossThickness" and q.is_a("IfcQuantityLength"):
                return q.LengthValue * declared_scale

    # 2. extrusion depth（声明单位）
    if elem.Representation:
        for rep in elem.Representation.Representations:
            if rep.RepresentationIdentifier != "Body":
                continue
            for item in rep.Items:
                if item.is_a("IfcExtrudedAreaSolid"):
                    depth = getattr(item, "Depth", None)
                    if depth and depth > 0:
                        return depth * declared_scale

    # 3. PCA 最小主轴（世界单位，斜板也对）
    pca = EX._pca_dims(elem, _GEOM_SETTINGS, world_scale)
    if pca and pca[0] > 0.005:
        return pca[0]

    # 4. bbox fallback（世界单位）
    b = _ifc_bbox(elem)
    if b:
        _, _, dz = _bbox_dims(b)
        if dz > 0.01:
            return dz * world_scale
    return None


# -------------------- 从 parser 输出收集提取值 --------------------

def collect_extracted(struct):
    """从 parser 输出收集提取值。返回 (out, ext_counts)
    out = {cat: [{...}]} 逐件项；
    ext_counts = {cat: int} 提取器对该类的模型级计数（用于仅计数的类别）。
    plan_elements 的 bbox 按 scale_info.world_scale 转成米。
    """
    out = defaultdict(list)
    ext_counts = defaultdict(int)
    scale_info = struct.get("scale_info", {})
    pe_scale = scale_info.get("world_scale", 1.0)  # plan_elements 原始单位 → 米
    for floor in struct.get("floors", []):
        # 逐层 structure 计数累加（stair/ramp/air_terminal 等仅计数类别）
        st = floor.get("structure", {})
        for cat, ckey in COUNT_KEYS.items():
            v = st.get(ckey)
            if isinstance(v, int):
                ext_counts[cat] += v
        # plan_elements：wall/door/window/railing 是主要/唯一来源；
        # beam/column/slab/pipe 等有带 id 的专门列表，避免重复收集。
        plan_has_railing = False
        for pe in floor.get("plan_elements", []):
            kind = pe.get("kind")
            bbox_raw = pe.get("bbox")
            if kind not in ("wall", "door", "window", "railing") or not bbox_raw:
                continue
            if kind == "railing":
                plan_has_railing = True
            bbox = _scale_bbox(bbox_raw, pe_scale)
            item = {
                "global_id": pe.get("global_id") or pe.get("id") or f"plan_{pe.get('name','?')}",
                "name": pe.get("name", ""),
                "bbox": bbox,
            }
            item.update(_length_thickness_height_from_bbox(bbox, kind))
            # door/window/railing 补宽/高
            if kind in ("door", "window"):
                dx, dy, dz = _bbox_dims(bbox)
                item["width_m"] = max(dx, dy)
                item["height_m"] = dz
            elif kind == "railing":
                dx, dy, dz = _bbox_dims(bbox)
                item["height_m"] = dz
                item["length_m"] = max(dx, dy)
            out[kind].append(item)

        # structural_elements: column/beam/slab/footing
        for se in floor.get("structural_elements", []):
            et = se.get("element_type", "")
            item = {k: v for k, v in se.items() if k in ("id", "name", "width_m", "depth_m",
                                                         "section_min_m", "section_max_m",
                                                         "thickness_m", "height_m", "span_m",
                                                         "volume_m3")}
            item["global_id"] = se.get("id")
            out[et].append(item)

        # pipes / pipe_fittings
        for p in floor.get("pipes", []):
            item = {"global_id": p.get("id"), "name": p.get("name", ""),
                    "diameter_m": p.get("diameter_m"), "length_m": p.get("length_m"),
                    "pipe_type": p.get("pipe_type")}
            out["pipe"].append(item)
        for p in floor.get("pipe_fittings", []):
            item = {"global_id": p.get("id"), "name": p.get("name", ""),
                    "diameter_m": p.get("diameter_m")}
            out["pipe_fitting"].append(item)

        # ducts / duct_fittings
        for d in floor.get("ducts", []):
            item = {"global_id": d.get("id"), "name": d.get("name", ""),
                    "duct_width_m": d.get("duct_width_m"), "duct_height_m": d.get("duct_height_m"),
                    "length_m": d.get("length_m")}
            out["duct"].append(item)

        # railings：plan_elements 已收（带 bbox 能算尺寸）；plan 没画时才退回 floor.railings
        if not plan_has_railing:
            for r in floor.get("railings", []):
                item = {"global_id": r.get("id"), "name": r.get("name", ""),
                        "height_m": r.get("height_m"), "length_m": r.get("length_m")}
                out["railing"].append(item)

        # rooms
        for r in floor.get("rooms", []):
            item = {"global_id": r.get("id"), "name": r.get("name", ""),
                    "area_sqm": r.get("room_area_sqm"), "type": r.get("type")}
            out["room"].append(item)

    return dict(out), dict(ext_counts)


# -------------------- 比对逻辑 --------------------

# 需要用名称/几何对齐的类别（提取侧没有可用的 GlobalId）
NAME_MATCH_CATS = {"wall", "door", "window", "stair", "ramp", "railing"}


def _bbox_center(b):
    """bbox (x0,y0,x1,y1,z0,z1) 的中心。"""
    return ((b[0]+b[2])/2, (b[1]+b[3])/2, (b[4]+b[5])/2)


def _dist3(a, b):
    return ((a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2) ** 0.5


def _scale_bbox(b, s):
    if not b:
        return None
    return (b[0]*s, b[1]*s, b[2]*s, b[3]*s, b[4]*s, b[5]*s)


def _it_center_m(item, scale):
    """构件的几何中心（米）。提取侧 bbox 已转米；真值侧 bbox_local 是模型单位需乘 scale。"""
    b = item.get("bbox")
    if b:
        return _bbox_center(b)
    bl = item.get("bbox_local")
    if bl:
        return _bbox_center(_scale_bbox(bl, scale))
    return None


def _match_by_name_or_geom(item, candidates, scale):
    """在候选列表里找同一个构件：按 (名称匹配等级, 几何中心距离) 排序选最优。

    名称匹配等级：0=完全同名，1=名称包含，2=无名称关系。
    关键：同名/包含可能有**多个**候选（老 Archicad 大量重名，如 IfcWall-6 ×4），
    必须再用几何中心距离在同类中选最近的，否则取"第一个"会错配（Jasmin 的 17 ✗
    就是这个原因）。无名称关系时只有中心 < 0.5m 才接受。
    ``item``/``candidates`` 可为真值项或提取项（bbox / bbox_local 均兼容，中心统一转米）。
    """
    t_name = (item.get("name") or "").strip().lower()
    t_center = _it_center_m(item, scale)

    best = None
    best_key = None
    for c in candidates:
        c_name = (c.get("name") or "").strip().lower()
        if t_name and c_name == t_name:
            rank = 0
        elif t_name and c_name and (t_name in c_name or c_name in t_name):
            rank = 1
        else:
            rank = 2
        cc = _it_center_m(c, scale)
        d = _dist3(t_center, cc) if (t_center and cc) else float("inf")
        key = (rank, d)
        if best_key is None or key < best_key:
            best_key = key
            best = c

    if best is None:
        return None
    rank, d = best_key
    if rank == 0:
        return best                       # 完全同名：取中心最近的那个
    if rank == 1:
        return best if d < 0.5 else None  # 名称包含：仍需几何接近
    return best if d < 0.5 else None      # 纯几何：< 0.5m


def build_crosscheck(truth, truth_scale, extracted, ext_counts=None):
    """返回每行一个字段对比的清单 + 汇总统计。"""
    rows = []
    stats = defaultdict(lambda: {"total": 0, "ok": 0, "wrong": 0, "missing_ext": 0, "extra_ext": 0})
    ext_counts = ext_counts or {}

    # 提取器仅计数的类别（无逐件输出）：做计数比对，避免误报逐件漏读。
    # 例如 stair / ramp / air_terminal / sanitary / outlet。
    for cat in [c for c in list(truth.keys())
                if c in COUNT_KEYS and not extracted.get(c)]:
        items = truth[cat]
        tcount = len(items)
        ecount = ext_counts.get(cat, 0)
        ok_all = (ecount == tcount)
        stats[cat]["total"] += tcount
        rc = "" if ok_all else f"提取器计数 {ecount} ≠ IFC 真值 {tcount}"
        for t in items:
            rows.append({
                "category": cat, "global_id": t["global_id"], "name": t["name"],
                "field": "计数(类整体)", "truth_value": tcount,
                "extracted_value": ecount,
                "verdict": "✓" if ok_all else "✗", "root_cause": rc,
            })
            if ok_all:
                stats[cat]["ok"] += 1
            else:
                stats[cat]["wrong"] += 1
        del truth[cat]

    # 提取侧 global_id 索引（有 id 的类别）
    ext_by_id = defaultdict(dict)
    ext_by_cat = defaultdict(list)
    for cat, items in extracted.items():
        for it in items:
            gid = it.get("global_id")
            if gid and not str(gid).startswith("plan_"):
                ext_by_id[cat][gid] = it
            ext_by_cat[cat].append(it)

    # 真值侧遍历，找对应提取值
    for cat, items in truth.items():
        truth_ids = set()
        ext_list = ext_by_cat.get(cat, [])
        matched_ext_ids = set()
        for t in items:
            gid = t["global_id"]
            truth_ids.add(gid)

            # 有 GlobalId 的类别走 id 对齐
            if cat not in NAME_MATCH_CATS and gid in ext_by_id.get(cat, {}):
                ext = ext_by_id[cat][gid]
                matched_ext_ids.add(gid)
            else:
                ext = _match_by_name_or_geom(t, ext_list, truth_scale)
                if ext and ext.get("global_id"):
                    matched_ext_ids.add(ext["global_id"])

            stats[cat]["total"] += 1

            if ext is None:
                rows.append({
                    "category": cat, "global_id": gid, "name": t["name"],
                    "field": "存在性", "truth_value": "有", "extracted_value": "无",
                    "verdict": "漏", "root_cause": "提取器未识别/未输出",
                })
                stats[cat]["missing_ext"] += 1
                continue

            # 按类别选比对字段
            compare = _fields_for(cat)
            for field, truth_getter, ext_key in compare:
                tv = truth_getter(t, truth_scale)
                ev = ext.get(ext_key)
                verdict = "?"
                root_cause = ""
                if tv is None and ev is None:
                    continue  # 两边都没有，跳过
                if tv is None:
                    # 真值缺该字段（如模型没导出 Qto 面积）→ 不可判，非提取错；
                    # 真正的"多读"由存在性级扫描上报。跳过避免虚报。
                    continue
                elif ev is None:
                    verdict = "漏字段"
                    root_cause = "提取器未输出该字段"
                elif isinstance(tv, (int, float)) and isinstance(ev, (int, float)):
                    if _close(tv, ev):
                        verdict = "✓"
                        stats[cat]["ok"] += 1
                    else:
                        verdict = "✗"
                        root_cause = _guess_root_cause(cat, field, tv, ev)
                        stats[cat]["wrong"] += 1
                else:
                    if tv == ev:
                        verdict = "✓"
                        stats[cat]["ok"] += 1
                    else:
                        verdict = "✗"
                        root_cause = "值不匹配"
                        stats[cat]["wrong"] += 1
                rows.append({
                    "category": cat, "global_id": gid, "name": t["name"],
                    "field": field,
                    "truth_value": _fmt(tv),
                    "extracted_value": _fmt(ev),
                    "verdict": verdict, "root_cause": root_cause,
                })

    # 提取侧多余的（在真值里没匹配上的）
    for cat, items in extracted.items():
        if cat not in truth:
            for it in items:
                rows.append({
                    "category": cat, "global_id": it.get("global_id", ""),
                    "name": it.get("name", ""),
                    "field": "存在性", "truth_value": "无", "extracted_value": "有",
                    "verdict": "多", "root_cause": "提取器多读/归类到不存在的类",
                })
                stats[cat]["extra_ext"] += 1
            continue
        truth_items = truth[cat]
        for it in items:
            matched = _match_by_name_or_geom(it, truth_items, truth_scale)
            if not matched:
                rows.append({
                    "category": cat, "global_id": it.get("global_id", ""), "name": it.get("name", ""),
                    "field": "存在性", "truth_value": "无", "extracted_value": "有",
                    "verdict": "多", "root_cause": "提取器多读/归类错误",
                })
                stats[cat]["extra_ext"] += 1

    return rows, dict(stats)


def _fmt(v):
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v) if v is not None else ""


def _fields_for(cat):
    """返回 [(字段名, 真值取值函数(t, scale), 提取器key)]"""
    def bbox_h():
        def getter(t, s):
            b = t.get("bbox_local")
            if not b:
                return None
            _, _, dz = _bbox_dims(b)
            return dz * s
        return getter

    def bbox_thickness():
        def getter(t, s):
            b = t.get("bbox_local")
            if not b:
                return None
            dx, dy, _ = _bbox_dims(b)
            return min(dx, dy) * s
        return getter

    def bbox_width():
        def getter(t, s):
            b = t.get("bbox_local")
            if not b:
                return None
            dx, dy, _ = _bbox_dims(b)
            return max(dx, dy) * s
        return getter

    if cat == "wall":
        return [
            ("厚度_m", bbox_thickness(), "thickness_m"),
            ("长度_m", bbox_width(), "length_m"),
            ("高度_m", bbox_h(), "height_m"),
        ]
    if cat in ("door", "window"):
        return [
            ("宽度_m", bbox_width(), "width_m"),
            ("高度_m", bbox_h(), "height_m"),
        ]
    def prism(key):
        def getter(t, s):
            raw = t["props"].get(key)
            return raw * s if raw is not None else None
        return getter

    if cat == "column":
        return [("截面_小边_m", prism("prism_min_raw"), "section_min_m"),
                ("截面_大边_m", prism("prism_mid_raw"), "section_max_m"),
                ("高度_m", prism("prism_big_raw"), "height_m")]
    if cat == "beam":
        # width_m = 截面小边（梁宽），depth_m = 截面大边（梁高），span_m = 真实长度
        return [("梁宽_m", prism("prism_min_raw"), "width_m"),
                ("梁高_m", prism("prism_mid_raw"), "depth_m"),
                ("跨度_m", prism("prism_big_raw"), "span_m")]
    if cat == "slab":
        def slab_th(t, s):
            # 真值已是米（read_ifc_truth 内用 world/declared 换算好）
            return t["props"].get("truth_thickness_m")
        return [("厚度_m", slab_th, "thickness_m")]
    if cat == "room":
        def room_area(t, s):
            raw = t["props"].get("truth_area_raw")
            return raw * s * s if raw is not None else None
        return [("面积_m2", room_area, "area_sqm")]
    if cat == "railing":
        return [("高度_m", bbox_h(), "height_m"),
                ("长度_m", bbox_width(), "length_m")]
    if cat == "pipe":
        # 直径/长度真值暂缺独立可靠来源（NominalDiameter 公称 ≠ 几何外径，
        # bbox 对斜管失真），先只做存在性/id 比对；直径校验待 Qto/profile 真值。
        return []
    return []


def _guess_root_cause(cat, field, tv, ev):
    if tv and ev:
        ratio = max(tv, ev) / max(min(tv, ev), 1e-9)
        if 900 < ratio < 1100:
            return "单位换算（疑似 mm/m 搞反）"
        if 2.5 < ratio < 4.0 and "直径" in field:
            return "直径 vs 半径 混淆"
    return "几何提取偏差（需下钻）"


# -------------------- 主流程 --------------------

def crosscheck_file(ifc_path):
    model = Path(ifc_path).stem
    struct = parse_ifc(str(ifc_path))
    # 用 parser 校准后的 world_scale 做真值单位（混合单位模型只用声明会错 1000 倍）
    world_scale = struct.get("scale_info", {}).get("world_scale", 1.0)
    truth, truth_scale = read_ifc_truth(ifc_path, world_scale=world_scale)
    extracted, ext_counts = collect_extracted(struct)
    rows, stats = build_crosscheck(truth, truth_scale, extracted, ext_counts)
    return model, rows, stats, struct


def write_outputs(model, rows, stats, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / f"{model}_crosscheck.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["category", "global_id", "name", "field",
                                          "truth_value", "extracted_value",
                                          "verdict", "root_cause"])
        w.writeheader()
        w.writerows(rows)

    # 汇总 md
    md = [f"# 互检清单 · {model}", "",
          "| 类别 | 真值总数 | 字段对 ✓ | 字段错 ✗ | 漏读(构件) | 多读(构件) | 漏字段 |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    ok_t = w_t = miss_t = extra_t = miss_field = total_t = 0
    for cat in sorted(stats.keys()):
        s = stats[cat]
        n_ok = s["ok"]; n_w = s["wrong"]; n_miss = s["missing_ext"]; n_extra = s["extra_ext"]
        n_mf = sum(1 for r in rows if r["category"] == cat and r["verdict"] == "漏字段")
        md.append(f"| {cat} | {s['total']} | {n_ok} | {n_w} | {n_miss} | {n_extra} | {n_mf} |")
        ok_t += n_ok; w_t += n_w; miss_t += n_miss; extra_t += n_extra
        miss_field += n_mf; total_t += s["total"]
    md.append(f"| **合计** | **{total_t}** | **{ok_t}** | **{w_t}** | **{miss_t}** | **{extra_t}** | **{miss_field}** |")
    md.append("")
    md.append(f"明细 CSV：`{csv_path.name}`")
    md.append("")
    # Top 根因
    rc = defaultdict(int)
    for r in rows:
        if r["verdict"] in ("✗", "漏", "多", "漏字段") and r["root_cause"]:
            rc[r["root_cause"]] += 1
    if rc:
        md.append("## 根因分布（Top 10）")
        md.append("")
        for k, v in sorted(rc.items(), key=lambda x: -x[1])[:10]:
            md.append(f"- {k}：{v}")
        md.append("")

    (out / f"{model}_summary.md").write_text("\n".join(md), encoding="utf-8")
    return csv_path, out / f"{model}_summary.md"


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="IFC file or directory")
    ap.add_argument("--out", default="output/crosscheck")
    args = ap.parse_args()

    target = Path(args.target)
    if target.is_file():
        files = [target]
    else:
        files = sorted(target.rglob("*.ifc"))
    files = [f for f in files if "temp_" not in str(f.name)]

    print(f"Found {len(files)} IFC file(s)")
    for fp in files:
        print(f"\n=== {fp.name} ===")
        try:
            model, rows, stats, _ = crosscheck_file(fp)
            csv_path, md_path = write_outputs(model, rows, stats, args.out)
            print(f"  rows: {len(rows)}  ->  {csv_path}")
            print(f"  summary -> {md_path}")
        except Exception as e:
            import traceback
            print(f"  FAILED: {e}")
            traceback.print_exc()


if __name__ == "__main__":
    main()
