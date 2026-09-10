# crosscheck 批量互检：剩余缺口根因清单（2026-09-10）

> 一批 16 模型全扫后，**核心几何互检全绿**（官方 9 版本 + ReferenceView + FZK 100% 字段正确）。
> 剩余缺口集中在几个模型，下面是逐项根因分类，作为 extractor 后续专项的清单。
> 总表：`output/crosscheck_v3/_batch_summary.md`

---

## 一、已达标（100% 字段正确）

Building-Architecture / Building-Structural × IFC2x3/4/4.3、Building-Hvac(IFC4/4.3)、wall-with-opening-and-window、**FZK-Haus**（108 构件 282 字段，含 4 类构件 + 房间面积）。
Revit-MEP 计数口径全对（air_terminal 43 / outlet 48 / sanitary 30）。

## 二、剩余缺口（按根因归类）

### 缺口 1 · Institute-Building（Archicad11 老导出）：wall/door/window 全漏（77+238+206）
- **现象**：5 层 `plan_elements` 全空；room/slab/column/stair 都对，唯独依赖 plan 的 wall/door/window 全漏。
- **根因假设**：老 Archicad 用 type-mapped 墙（构件无直接 Body 几何，走 IfcRepresentationMap），`_elem_world_bbox` 取不到 → plan_elements 为空。
- **修复方向**：plan/bbox 读取对 MappedItem 解引用（A3 已给结构构件做过 `_extrusion_profile_info`，plan/bbox 侧需同样处理）。
- 严重度：中高（真实项目、量大）。

### 缺口 2 · Basic-Sample & Building-4351（Revit）：slab/footing 不进 structural_elements 逐件
- **现象**：structure 计数有（slabs=4/层、footings=20），但 `structural_elements` 里 slab/footing 为空 → 逐件漏读。
- **根因假设**：Revit 导出的 slab/footing 在 `_structural_sections` 被厚度/截面过滤静默丢弃（或 fallback z 分配遗漏），需查 thickness 判定对该批构件的返回值。
- **修复方向**：对这两模型的 slab/footing 逐件打点 `_slab_thickness_m` / `_extrusion_profile_info`。
- 严重度：中（结构性审查依赖 slab/footing）。

### 缺口 3 · Jasmin-Sun（Archicad9）：wall 高度真值 5m vs 提取 2.75m（27 个 ✗）
- **现象**：跨 2 层的一堵墙，真值 IFC 一条（高 5m），提取按楼层出两条 2.75m → 高度 ✗；同名不同尺寸的窗/墙在名称匹配里错配。
- **根因假设**：跨层构件的楼层归属 + 同名多实例匹配歧义（交叉验证算法侧）。
- **修复方向**：① 匹配器同名命中多个时按几何中心+尺寸就近（算法侧，惠多模型）；② 是否把跨层墙拆层归属，需与"每层出一次供平面审查"的产品逻辑权衡。
- 严重度：低-中（值偏差非崩溃，老导出）。

### 缺口 4 · Building-4351（Revit）railing 漏 5 + stair 计数 3 vs 4 + Generic slab 漏
- **现象**：railing 11 真值读 6；stair 计数差 1；4 块 Generic slab 漏（同缺口 2）。
- **根因假设**：railing 部分无 Body 几何 / 超出 plan cap；stair 1 根归类成 flight；slab 同缺口 2。
- 严重度：低（4351 为教学样例）。

### 缺口 5 · Building-Hvac IFC2x3：pipe 多读 1
- **现象**：IFC2x3 无 IfcPipeSegment（schema），真值 0；提取器把某 flow segment 归 pipe → 多 1。
- **修复方向**：2x3 管道真值用 `IfcFlowSegment` 别名（或直接按已知 schema 差异豁免）。
- 严重度：极低。

---

## 三、通用建议（跨模型收益）

1. **window/door 尺寸应属性优先**（OverallWidth/OverallHeight），当前 crosscheck 与 plan 都用 bbox（含窗框/台），Archicad 类模型误差大。
2. **匹配器同名歧义**：同名多实例时用几何中心+尺寸双重约束就近（Jasmin 27 个 ✗ 里一部分是错配而非读错）。
3. **老导出 type-mapped 构件**：bbox/plan 路径解引用 MappedItem（Institute wall 全漏的钥匙）。

## 四、本轮结论（可进汇报）

- 互检已从"官方基准 + FZK 两样板"铺到 **16 个模型的批量对错总表**；
- 官方全套 + FZK + Revit-MEP 计数 **100% 字段正确**；
- 剩余缺口的价值在"清单化"——每项都能量化到具体构件/类别/根因，是 extractor 下一轮专项的输入。
