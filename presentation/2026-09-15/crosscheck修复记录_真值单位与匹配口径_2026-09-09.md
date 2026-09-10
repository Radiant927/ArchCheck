# crosscheck v2 修复记录：真值单位 + 匹配口径（2026-09-09）

> 改动：`scripts/crosscheck_ifc.py`（互检工具自身）+ `bim/extractor.py`（A3 几何修复，见前文）
> 触发：A3 完成后把 crosscheck 铺到更多模型，暴露一批"对不齐/口径"问题，非 extractor 真 bug。

---

## 一、修复清单

| # | 问题 | 根因 | 修法 |
|---|---|---|---|
| 1 | Building-Structural 全报 mm/m 搞反 1000 倍 | 混合单位模型（声明 mm、几何实际 m），crosscheck 真值侧只读声明单位 | 复用 parser 校准的 `scale_info.world_scale` 传进 `read_ifc_truth` |
| 2 | railing 漏 2 多 4（空名栏杆） | 真值 bbox 是局部坐标、提取侧是世界坐标 → 几何中心兜底匹配失败（其余类别靠名字匹配成功才没暴露） | `_ifc_bbox` 打开 `USE_WORLD_COORDS=True`，两侧同参照系 |
| 3 | 反向匹配全失败 → 多读误报 | 匹配函数把真值项当候选时读 `bbox_local`，而函数只认 `bbox`（已转米），单位/键不一致 | 重写为对称匹配器 `_match_by_name_or_geom`：统一归一几何中心（bbox 已米 / bbox_local 乘 scale），正反两向复用 |
| 4 | room 多读 7 | 真值侧没加 IfcSpace 类别 | TYPE_MAP 加 IfcSpace；面积真值从 `IfcElementQuantity.GrossFloorArea/NetFloorArea`（Qto）取 |
| 5 | stair / air_terminal / sanitary / outlet 全报漏读 | 提取器对这四类**只汇总计数不逐件输出**，逐件比对必然误报 | 提取器不逐件的类别改走"计数比对"（读每层 structure 计数求和 vs by_type 真值计数）；无逐件也无计数的类型（IfcDuctFitting/IfcLightFixture）从 TYPE_MAP 移除 |
| 6 | beam/slab/column 潜在重复收集 | plan_elements 与 structural_elements 重复输出同一实体 | plan_elements 只收 wall/door/window/railing（无带 id 专门列表的类别） |

---

## 二、修复后互检结果

### FZK-Haus（真实住宅）—— 全绿

| 类别 | 真值 | ✓ 字段 | ✗ | 漏 | 多 | 说明 |
|---|---:|---:|---:|---:|---:|---|
| beam | 51 | 153 | 0 | 0 | 0 | 宽/高/跨度逐根 ✓（A3 PCA） |
| room | 7 | 7 | 0 | 0 | 0 | **面积与 Archicad Qto 精确一致**（11.53 vs 11.5 等） |
| wall | 26 | 78 | 0 | 0 | 0 | |
| window | 11 | 22 | 0 | 0 | 0 | |
| door | 5 | 10 | 0 | 0 | 0 | |
| slab | 4 | 4 | 0 | 0 | 0 | 含斜屋顶板（A3） |
| column / railing / stair | 1/2/1 | 3/4/1 | 0 | 0 | 0 | |
| **合计** | **108** | **282** | **0** | **0** | **0** | |

### 官方样例回归

| 模型 | 结果 |
|---|---|
| wall-with-opening-and-window | 墙/窗 5/5 ✓（无回归） |
| Building-Structural (IFC4) | beam 18 + wall 12 全 ✓（单位修复生效） |
| Building-Hvac (IFC4) | air_terminal 计数 2/2 ✓ |
| Revit-MEP-Sample | parse 计数与基线一致（pipes 868/fittings 665/ducts 207），A3 重构未破坏 MEP |

---

## 三、追加修复：Building-Architecture slab 漏读（extractor 第三类斜构件 bug）

**现象**：官方 IFC4 Building-Architecture 的 3 块板只读出 1 块（B=66.7 那个"固定缺口"），crosscheck 精确定位为两块屋顶板漏读。

**根因**（打点确认）：两块屋顶板是**倾斜的 Tessellation（IfcTriangulatedFaceSet）板**，无 Qto 也无 ExtrudedAreaSolid，`_slab_thickness_m` 兜底用**世界坐标 bbox 的 Z 差**当板厚 → 斜板世界 Z 差 = 屋脊高差（2.8m / 4.2m），超过滤范围（<1.0m）被 `_structural_sections` 静默丢弃 → 板没输出。

**这暴露了同类 bug 的第三层**：
- A3-1 修了**斜板**（FZK 屋顶板，extrusion 表示 → 用 ExtrusionDepth）；
- 但官方样例屋顶板是 **Tessellation 网格**（无 extrusion），退到世界 bbox 兜底又错；
- 即"斜构件 bbox 失效"在非拉伸体表示上依然存在。

**修法**：`_slab_thickness_m` 兜底从"世界 bbox Z 差"改为 **PCA 最小主轴**（`_pca_dims` 的 small）——板是扁平面板，无论怎么斜，最薄方向永远是板厚。真值侧 `_truth_slab_thickness` 同步（避免两边口径不一）。水平板 PCA small ≈ dz，斜板 PCA small ≈ 真实厚度。

**修复后**：Building-Architecture slab **3/3 ✓**（0.25 / 0.32 / 0.34 vs 同法真值），wall 4×3 ✓；FZK 与官方样例回归全绿。

**至此几何提取口径统一为**：Qto → ExtrudedAreaSolid.Depth → PCA 最小主轴 → bbox Z（纯兜底），斜板/斜梁/网格表示全覆盖。

## 四、遗留口径说明

- room 面积仅在模型带 Qto 面积时有真值可比（Building-Architecture 无 Qto → 只比存在性不标 ✓）。
- duct 尚无逐件字段比对（真值侧没读宽/高），非错误，是后续补全点。
- crosscheck 大模型（如 Revit-MEP）真值侧逐件 create_shape 慢，当前回归用 parse 计数替代。

## 五、追加修复：Revit(mm-declared) 板厚单位通病（2026-09-10）

**现象**：Basic-Sample(Revit) slab 全漏（structure 计数有、逐件空）；打点发现 `_slab_thickness_m` 返回 **150~6000**（毫米当米）。

**根因**：Revit 导出声明长度单位 mm、但几何实为米级（混合单位）。`_structural_sections` 把"单位推断不自信"的 `profile_scale=None` **错误覆盖成 world scale(=1)**，于是 Qto 板厚 247mm 没乘 0.001 → 读到 247m，超过滤范围（<1m）被丢弃。

**修法**：
- `_structural_sections` 不再把 `profile_scale=None` 覆盖成 scale；None 表示"Qto/profile 单位不可信"。
- `_slab_thickness_m` 加 `profile_scale` 门控：仅当 profile_scale 可信时读 Qto/Extrusion（乘 profile_scale），否则直接走 PCA/bbox（世界几何，单位可靠）。
- beam/column/footing 的 `_extrusion_profile_info` 同样在 profile_scale 为 None 时跳过（走 PCA/bbox）。
- crosscheck 真值侧 `_truth_slab_thickness` 同步：Qto/Extrusion 乘 declared_scale、PCA/bbox 乘 world_scale，直接产出米。

**修复后**：
- Basic slab 12✗ → **11✓ 1✗**；footing 由 0 → 12 逐件（11 仍未进逐件，Revit 归属更深缺口）。
- FZK（板 4/4）、Building-Architecture（3/3）**无回归**。
- 惠及所有 mm-declared/geometry-m 的 Revit 类模型。

**教训**：Qto/Extrusion 用**模型声明单位**、PCA/bbox 用**世界几何单位**，两者不可混用一个 scale — 这是继"斜构件 bbox 失效"之后第二个跨模型的系统性坑。

## 六、追加修复：Institute 平面提取闸门 + 墙真值双算（2026-09-10）

**现象**：Institute-Building(Archicad11) 的 wall 238 / window 206 / door 77 在互检里**全部报漏读**，平面图空白。

**根因（实测更正了最初误判）**：
- 墙/门/窗**其实都在楼层容器里**（`structure.walls=119` 等计数正常）。真因是 `extract_plan` 闸门：`total_phys` 把 **110 个 IfcAnnotation + 253 个 IfcFurnishingElement（挂在 IfcSpace 下）** 也算进去 → `809 > 600` → 平面提取被关 → `plan_elements=[]`。而 crosscheck 对墙/门/窗只从 `plan_elements` 取数 → 逐件全漏。
- 附带：`TYPE_MAP` 并列 `IfcWall` 与 `IfcWallStandardCase`，而 `by_type("IfcWall")` 已含子类 → 墙真值双算成 238（实际 119）。FZK 同样被双算（26→实为 13）。

**修法**：
- **A**（主修）`extractor.py`：`total_phys` 改为只数 `_plan_element_kind` 命中的构件（忽略 Annotation/Furnishing/Space）→ Institute 809→442，闸门开启；Snowdon/Revit-MEP 仍 >600 保持不变。
- **B**（防御性）新增 `wall_door_window_fallback`：仿 structural/football，把**未包含**的墙/门/窗按世界 z 中心分到楼层（用 seen 去重，因 by_type 含子类）。对 Institute 空操作，惠及 Basic-Sample(5 扇无楼层门)等。
- **C** 把 fallback 并入 `plan_elements` 输入与逐层计数/门宽（用独立变量 `wdw_fb`，不重绑 `els`）。
- **D** crosscheck `TYPE_MAP` 移除 `IfcWallStandardCase`（by_type 已含子类）。

**不改什么**：门关联/疏散链（`door_storey`/`_associate_doors`）完全不动，避免 fallback 门干扰同层门控；`_plan_elements` cap 不变；`qa_validator` 不受影响。

**修复后**：
- Institute crosscheck：wall 119 / window 206 / door 77 **全部读到，0 漏**（原 521 漏）；1042 字段 ✓ / 23 ✗（字段级小偏差）。
- 平面：每层 plan_elements = [85,107,109,108,33]。
- benchmark：Institute **A=100 B=100**（wall 119/119、door 77/77、window 206/206 全满），总分 88.8 A（开平面使 F 性能轴略降，89.9→88.8，仍 A）。
- 代价：Institute 解析 ~2s→~14s（tessellate 442 件），仅"需平面图"的模型发生。

**教训**：`total_phys` 这类"模型复杂度闸门"必须只数**功能相关的构件**，否则被 Annotation/Furnishing 这类"凑数"元素误触发，把该出的平面图关掉。
