# ArchCheck V3.0 项目总览

> AI 多层建筑合规审查平台 — 角色化多 Agent · 确定性规则判定 · AI 隐形语义预处理 · 逐构件互检验真 · 二维/三维可视化
> 更新日期：2026-09-17
> 上一版：V2.0（2026-08-27，47 条规则、结果页 V2.1、B-Rep 调研结论）。本版新增：互检验真体系、31 模型六维基线、MEP 提取增强、AI 语义预处理层、交互 viewer 与三维调研启动；规则增至 **50 条/地区**。

---

## 1. 项目定位

ArchCheck 是面向**多层建筑**的规范合规自动审查平台：把设计师交付的 **BIM（IFC）模型**完整读取、校验、判定，输出**带规范依据、可复算、可审计**的审查报告。

- **输入**：IFC2x3 / IFC4 / IFC4.3 真实模型或自建样例
- **输出**：模型可用性 QA + 六专业审查结果 + 平面/剖面/三维视图 + HTML/Excel/BCF/COBie 报告
- **标准**：CN GB ↔ SG Fire Code 2023 一键切换（双语 UI），丢规则包文件夹即可扩展
- **底线原则**：**模型负责读懂，规则负责判**。合规判定 100% 由确定性规则完成；LLM 只做语义读懂、叙述解释，不判定、不改几何数字
- **数据诚实**：不知道标 Unknown，缺字段标"未检查（缺字段 X）"，参数标 🟢来自模型 / 🟠默认待填，宁可弃权不假通过

## 2. 系统架构

### 2.1 五个角色化 Agent + 一个隐形 AI 层

```
IFC 上传
  │
  ▼
① BIM Reader          解析 IFC（几何/属性/材料/名称/拓扑）+ 模型可用性 QA（健康度 0-100，致命阻断）
  │
  ▼
ⓔ AI 语义预处理层（新增，隐形，agents/enricher.py）
  │     只把关键词拿不准的语义归一化：房型 / 材料类 / 管道系统
  │     受控枚举 · 几何只读 · 一次批量调用 · 哈希缓存 · 失败降级
  ▼
② Compliance Judge    确定性判定：六专业 50 条规则，多标准规则包
  │                     值 vs 阈值 · 动态阈值（公式/LLM）· 跨楼层聚合 · 冲突检测 · 缺字段诚实上报
  ▼
④ Reasoner            LLM 综合：审查叙述 · 跨专业冲突协调 · 处置建议
  ▲
  └──── ③ KB Steward    规范知识库 RAG：动态取值 · 条文→JSON 规则生成

⑤ Independent Reviewer  检索 RAG 规范原文复核判定（概念保留，结果页不显示）
```

| 组件 | 职责 | 代码 | 确定性 |
|---|---|---|---|
| ① BIM Reader | IFC 解析 + QA 体检 | `bim/parser.py` `bim/extractor.py` `bim/qa_validator.py` | ✅ |
| ⓔ Enricher | 判定前隐形语义归一化（房型/材料/管道） | `agents/enricher.py` | 关键词部分 ✅；LLM 只填空、枚举校验 |
| ② Compliance Judge | 六专业规则判定 | `core/engine.py` | ✅ |
| ③ KB Steward | 规范 RAG、动态阈值、规则生成 | `kb/steward.py` `data/rag_kb/` | 混合（检索确定，生成用 LLM） |
| ④ Reasoner | 审查叙述、冲突协调 | `llm/client.py` | LLM（只叙述不判定） |
| ⑤ Reviewer | 规范原文复核（UI 已撤，概念保留） | `agents/reviewer.py` | ✅ |
| （仲裁员） | 9/14 旧方案"判定后 AI 仲裁"，已被 enricher 取代 | `agents/arbitrator.py` | 代码保留、**不挂载** |

### 2.2 AI 语义预处理层的五条工程约束（9 月核心成果）

1. **只填空**：关键词已高置信分类的不重判，只送 Unknown/低置信对象；
2. **几何数字零写入**：AI 只能写房型/材料类/管道系统三个枚举字段，尺寸面积距离计数对它只读；
3. **受控词表 + 枚举校验**：房型 7 选 1、材料 6 选 1、管道 6 选 1，越界值直接丢弃；
4. **集中记账可追溯**：每条结论 `{原值→新值, 来源, 置信度, 理由}` 写入 `bdata["_enrichment"]`；
5. **整栋一次调用 + 内容哈希缓存 + 优雅降级**：无 API/断网/非法返回时行为与纯关键词完全一致。

关键一课：实测发现 AI 会"凭房间面积猜用途、把泛型楼板默认成混凝土"（真实幻觉风险），prompt 迭代到 v3——房间候选**只发名字不发尺寸**、纯编号必须弃权、词表外功能必须弃权、缓存键含 prompt 版本。

## 3. 审查流水线

```
上传 IFC + 选标准
  → ① QA 体检（长度单位/空间完整性/几何有效性/边界引用 + 实体覆盖度统计；致命问题阻断）
  → ⓔ AI 语义归一化（仅 IFC 上传分支；演示/手工编辑数据有意不启用）
  → ② 六专业逐层判定（消防/无障碍逐房间，电气逐设备，结构逐构件，机电逐管道风管，整楼聚合）
  → 缺字段规则转"未检查（缺字段 X）"；全字段为空的规则折叠，不刷屏
  → 冲突检测（同层同位置跨专业，bbox 缓存加速）
  → ④ LLM 审查叙述
  → 结果页：统计卡 + 双栏（判定列表 + 平面/3D 视图）+ 专业筛选 + "交互查看"Tab + 导出
```

## 4. 已实现能力

### 4.1 BIM Reader（九月大幅增强）

- 建筑：楼层/房间（几何面积）/门宽（属性→名称→bbox 三级回退）/墙梁柱板/楼梯/栏杆/楼板占地/英制单位推断
- **MEP 增强**：管件配件、数量集、材料、系统分类、Qto-Profile 单位抽样推断；**管道网络拓扑**（端口连接/系统归属/系统名回填管型，pipe_type 识别 29%→86%）；消火栓间距由消防管 bbox 中心推算
- **几何修复（互检驱动，逐件）**：GlobalId 对齐 + 就近消歧匹配、footing/栏杆/楼梯休息平台、英制单位、斜构件/MappedItem 等
- QA 体检：健康度评分 + 致命阻断 + **实体覆盖度统计**（模型有、平台没读的类型如实上报）
- 性能：clash 检测缓存各元素 bbox，Lab.ifc 解析 49s → 4.4s

### 4.2 Compliance Judge — 六专业 50 条/地区

规则包 `data/standards/{cn,sg}/`：消防疏散 13 / 机电 **13**（含未知系统管道普适兜底）/ 全楼 9 / 电气 6 / 无障碍 5 / 结构 4。

- 8 操作符 + 条件过滤 + **`conditions_all` 多适用条件 AND**（9 月新增；如 STR-001 木/钢/砌柱不适用最小混凝土截面规则，从源头消除木柱误报）+ scope 分发 + 跨楼层聚合 + 冲突检测
- **缺字段诚实上报（coverage）**：模型没有规则要的字段→"未检查（缺字段 X）"，补上字段自动激活
- **动态阈值**：公式（梁高 max(0.2, min(span,6)/20)）→ RAG/LLM → 静态回退，按规则+上下文缓存
- 真实几何量：房间邻接图+Dijkstra 疏散距离、房间最远点采样、门宽/出口数、柱梁板截面、坡道坡度、管径、消火栓间距

### 4.3 KB / Reasoner / Reviewer

- RAG 语料 `data/rag_kb/`：免费规范全文（FC2023、AD、Accessibility 2025、GB 55037/55036 OCR 等 36 份），付费标准仅索引（版权合规）；条文→LLM→JSON 规则→校验→人工确认
- Reasoner：专业叙述、跨专业冲突协调；DeepSeek **官方 API 直连**（密钥仅存本机 git 忽略配置）
- Reviewer：纯确定性条文检索复核，UI 不展示（付费标准无全文会全"待人工"），架构概念保留

### 4.4 可视化与交互

- **结果页 V2.1**：按 Agent 组织、双栏、3D 等轴视图、楼层俯视/剖面、专业筛选、标准切换对比、HTML/Excel/PNG 导出
- **二维交互 viewer（收尾中）**：Pillow 高清平面底图 + plotly 透明热区；悬停 tooltip（名称/IFC 类型/楼层/关键尺寸/互检状态）、点击详情面板（三轴尺寸/GlobalId/材料含 AI 标注/触发规则 ID 与条文）；独立演示页 `presentation/2026-09-22/demo/FZK-Haus_..._viewer_demo.html`；静态 web 版在 `web/viewer/`（web-ifc.wasm）+ `web/serve.py`
- **互检标注图**：✓绿/✗红（引线"真值→提取值"）/漏橙虚框/多紫/灰，按真实坐标落到各层平面图

## 5. 质量保障体系（九月新建，项目可信度的核心论据）

### 5.1 逐构件互检 crosscheck（IFC 真值 vs 平台提取值）

`scripts/crosscheck_ifc.py` + `run_crosscheck_batch.py` + `render_crosscheck_annotated.py`：按 GlobalId 逐件比对分类/几何/计数，分层抽样人工复核。

v6 结果：FZK-Haus 103 件全绿（仅 2 个纯编号房间的类型分类存异）；Jasmin-Sun（Archicad9 老导出）几何 77.5%→**100%**，仅余 1 段栏杆计数口径；Basic-Sample 唯一红色是楼梯休息平台被建模成楼板（建模口径，非提取错误）；**建筑类模型几何正确率 99%+**。残留短板：MEP 管长互检 64.5%（部分管件非拉伸体几何，随三维几何调研解决）。

### 5.2 31 模型六维基线测评

测试集 `bim/test-suites/`（31 个 IFC）：`official/`（IFC2x3/4/4.3/ReferenceView 官方基准）、`real-project/`（9 个真实项目：FZK、Jasmin、HITOS、Smiley、4351、Basic 等）、`mep/`（bridge/electrical/hvac/plumbing/structural）。

六维：A 健壮性 / B 提取完备 / C 字段填充 / D 几何准确 / E 规则激活 / F 性能（脚本 `benchmark_ifc.py`、`run_full_benchmark.py`）。

- **7 个真实建筑模型达 S/A 级**；结论：读取能力已近解析天花板，下一瓶颈是规则数据覆盖
- FZK-Haus 91.0 **S**（B/D/F 满分，墙13门5窗11梁51板4全读，26 条真违规）
- Revit-MEP 84.3 **A**（2251 个机电实体全读、1034 条问题分 High/Low/Missing；无房间触发 QA 阻断，A 诚实降档）
- 官方 Building-Architecture 76.1 **B**（三版本读数一致，晒出 slab 1/3 读漏的固定缺口）

### 5.3 语义层 34 题金标

`scripts/semantic_gold.json` + `benchmark_enrichment.py`（21 房型 + 13 材料，含一批"正确答案就是 Unknown"的反幻觉题）：

| 类别 | 总准确率 | 可归类覆盖率 | 已归类精确率 | 乱猜 |
|---|---|---|---|---|
| 房型 | 81.0% → **90.5%** | 33.3% → 42.9% | 100% | **0 → 0** |
| 材料 | 61.5% → **100%** | 30.8% → 69.2% | 100% | **0 → 0** |

安全性回归：FZK / FZK-A11 / Jasmin 增强 off→on，违规总数变化 **0**、几何计数零变化。大样本触发/弃权统计待本周完成。

## 6. 数据与标准

- **规则**：CN / SG 各 50 条，配置化扩展（`data/standards/<code>/` 丢文件夹即出现）
- **测试模型**：31 模型测试集（上）+ 自建 Office 3F（3 层 24 房完整办公楼，管线回归用）+ 仓库内置 Lab.ifc / Snowdon Towers
- **知识库**：36 份文档清单 `scripts/rag_kb/kb_manifest.json`，免费全文/付费索引边界清晰

## 7. 技术栈

| 层 | 技术 |
|---|---|
| Web | Streamlit（app.py，约 1500 行） |
| BIM | ifcopenshell + networkx（疏散图）+ Pillow（平面/标注图） |
| 判定 | Python + JSON 规则引擎（自研，确定性） |
| LLM | DeepSeek 官方 API（`requests` 直连），磁盘哈希缓存 |
| RAG | 本地语料 + pypdf/pymupdf/rapidocr |
| 二维交互 | plotly 热区；独立 HTML 演示页 |
| 三维（调研中） | `web-ifc-viewer/`（That Open Engine / web-ifc，已装依赖）；候选含 xeokit-sdk、Speckle、three.js、FreeCAD/Bonsai |
| 导出 | HTML / Excel / BCF 2.1 / COBie |

## 8. 当前阶段与下一步（2026-09-22 计划，两条线并行）

**Viewer 线（导师最关注）**：
1. 二维快速收尾——悬停即有 tooltip、点击详情面板、问题列表↔图上构件双向高亮联动、修无房间边缘模型显示；
2. **三维开源选型调研立即推进**（已 clone That Open Engine）：完整加载老导出/斜构件/MappedItem、按 GlobalId 拾取高亮、与 Python 架构衔接、license、FZK→2000+ 管件性能、AI 挂点；产出选型报告 + 2-3 个真实 IFC 最小加载实测；
3. 三维查看器原型 → 三维 AI（自然语言定位构件、AI 通俗解释违规、框选区域汇总；AI 仍只解释不判定）。

**语义线收尾（"要做完"）**：B1 31 模型大样本实测；B2 住宅房型词表（Living/Bedroom/Kitchen 等）+ 多语言关键词 + **配套规则同步新增**；B3 归一化从 `build_review_data` 后前移进 `parse_model` 的评估（互检分类维度 24.2% 待提升）；B4 管道系统真实 MEP 实测；B5 自由描述入口仅预留。

顺带：MEP 管长互检 64.5%→90%+；互检 A4 扩属性/Pset 维度。

## 9. 已知边界（如实）

1. 房型词表偏公共建筑：住宅客厅/卧室、储藏、接待无处可归，AI 只能弃权（词表/规则覆盖问题，不靠硬映射）
2. 归一化目前在送审数据层，互检"原始分类"维度暂不受益（前移评估中）；仅 IFC 上传分支启用
3. MEP 管长 64.5%：非拉伸体管件几何口径未统一
4. 几何近似量：管径 bbox 量取、`has_sprinkler` 近邻近似、最远疏散距离凸包+网格采样（规则 description 内标注需复核）
5. 固定构造阈值：STR-002 梁高公式为工程近似；STR-003 板厚静态 0.1m
6. 付费标准无全文：相关判定不给自动原文证据，需人工对照（Reviewer 显示已撤）
7. 稀有字段（照度、耐火等级、疏散指示灯具）公开模型普遍缺失→规则停在"未检查"，不构造默认值
8. 大模型性能：几何曲面化一次性代价高（已有 bbox 缓存等优化）

## 10. 快速开始

```bash
cd ArchCheck
pip install -r requirements.txt
streamlit run app.py            # 默认 http://localhost:8501
# 上传 .ifc（bim/test-suites/real-project/FZK-Haus_*.ifc 等），选标准，开始审查
```

常用脚本：

| 用途 | 脚本 |
|---|---|
| 六维批量基线测评 | `scripts/benchmark_ifc.py`、`run_full_benchmark.py`、`analyze_benchmark.py` |
| 逐构件互检 + 标注图 | `crosscheck_ifc.py`、`run_crosscheck_batch.py`、`render_crosscheck_annotated.py` |
| 二维交互 demo 页 | `scripts/build_viewer_demo.py` |
| 语义金标基准 + 图表 | `benchmark_enrichment.py`、`plot_enrichment_benchmark.py`、`semantic_gold.json` |
| 三维最小加载 | `web/viewer/`（静态）、`web-ifc-viewer/`（That Open 调研区） |
| 知识库 | `scripts/rag_kb/`（建库/OCR/清洗/条文生成规则） |

## 11. 关键文档索引

- 阶段计划：`presentation/2026-09-22/总体工作计划_二维Viewer收尾与三维AI审查_2026-09-22.md`
- 语义层方案与周报：`presentation/2026-09-15/AI语义预处理层方案设计_*.md`、`本周工作汇报_互检验真与AI语义预处理_*.md`
- 31 模型测评：`docs/规划与技术/实用性测试报告与改进计划_2026-09-08.md`、`presentation/2026-09-08/`（PPT、讲稿、三类代表解读）
- 路线图与行业标准：`docs/规划与技术/真实可用_目标路线图_行业标准.md`
- 历次汇报材料：`presentation/2026-08-13/` 起按日期分文件夹
