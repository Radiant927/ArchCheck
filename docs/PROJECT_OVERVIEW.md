# ArchCheck V2.0 项目总览

> AI 多层建筑合规审查平台 — 角色化多 Agent 架构 · 多专业审查 · BIM/IFC 输入 · RAG 知识库
> 更新日期：2026-08-12（同步 UI V2.1 与 Office 样例）

---

## 1. 项目定位

ArchCheck 是一个面向**多层建筑**的规范合规自动审查平台。核心价值：把设计师交付的 **BIM（IFC）模型**中所有建筑信息读取、校验、判定，并给出**带规范依据**的审查报告。

- **输入**：IFC（BIM）文件（真实模型或自建样例）
- **输出**：模型可用性报告 + 分专业（消防/电气/结构/无障碍）审查结果 + 生成平面图（3D/俯视/剖面）+ HTML/Excel 报告
- **标准**：CN GB ↔ SG Fire Code 2023 一键切换（双语 UI），可配置扩展
- **数据诚实**：审查基于模型真实数据；房间类型不知道标 Unknown，参数标 🟢来自模型 / 🟠默认·待填写

## 2. 架构：5 个角色化 Agent

从早期"按专业分工（Civil/EEE/Building/Coordinator）"重构为**按职责分工**：

```
IFC 上传
  │
  ▼
① BIM Reader       解析 IFC + 模型可用性 QA（健康度评分 0-100，致命问题阻断）
  │
  ▼
② Compliance Judge 确定性判定：消防/电气/结构/无障碍 四专业，多标准规则包
  │                    值 vs 阈值 · 动态阈值（公式/LLM）· 跨楼层聚合 · 冲突检测
  ▼
⑤ Independent Reviewer   检索 RAG 规范原文复核判定 → ✅已复核 / ⚠️待人工复核 + 证据
  │
  ▼
④ Reasoner         LLM 综合：审查叙述 · 跨专业冲突协调 · 处置建议
  ▲
  └──── ③ KB Steward   规范知识库 RAG：动态取值 · 条文→JSON 规则生成
```

| Agent | 职责 | 代码 | 是否确定性 |
|---|---|---|---|
| ① BIM Reader | IFC 解析 + 模型可用性 QA | `bim/parser.py` + `bim/extractor.py` + `bim/qa_validator.py` | ✅ 确定性 |
| ② Compliance Judge | 四专业规则判定 | `core/engine.py` | ✅ 确定性 |
| ③ KB Steward | 规范 RAG、动态阈值、规则生成 | `kb/steward.py` + `data/rag_kb/` | 混合（检索确定性，生成用 LLM） |
| ④ Reasoner | 审查叙述、冲突协调 | `llm/client.py` | LLM |
| ⑤ Independent Reviewer | 规范原文复核（**概念保留，结果页不显示**） | `agents/reviewer.py` | ✅ 确定性 |

设计原则：**"模型负责读和说，规则引擎负责判"**——合规判定保持确定性、可解释、可审计；LLM 只做叙述/协调/生成。

## 3. 已实现能力

### 3.1 BIM Reader — 模型可用性
- IFC 解析：楼层/房间（几何面积）/门宽（属性→名称→几何 bbox）/构件统计/单位推断
- 模型 QA 四项：长度单位、空间完整性、几何有效性、空间边界引用
- **健康度评分（0-100）** + 致命问题阻断（空壳/无几何/无楼层）

### 3.2 Compliance Judge — 四专业判定
- 规则引擎：8 操作符 + 条件过滤 + 跨楼层聚合 + 冲突检测
- 规则包：`data/standards/{cn,sg}/{civil,eee,building,structural}_rules.json`
- **动态阈值**：`dynamic_threshold` 规则字段，公式（如梁高 max(0.2, min(span,6)/20)）→ RAG/LLM → 静态回退，按规则+上下文缓存
- 真实数据：疏散距离（房间邻接图+Dijkstra）、门宽、出口数、柱/梁/板截面、坡道坡度

### 3.3 KB Steward — 规范知识库
- RAG 语料：`data/rag_kb/`（免费核心全文 + 付费标准索引）
- **规则生成**：规范条文 → LLM → JSON 规则 → 校验 → 人工确认（`scripts/rag_kb/generate_rules_from_rag.py`）
- 清洗/OCR 工具：`cleaning_rules.py`（过期引用检测）、`ocr_pdf.py`（扫描 PDF 转文本）

### 3.4 Independent Reviewer — 独立复核（概念保留）
- 机制：对每条违规按 code_ref 检索免费语料，命中 → 已复核 + 证据片段；付费标准 → 待人工
- 纯确定性文本检索，无 LLM 循环
- **UI 显示已移除**：因演示规则多引用付费标准、语料没有 → 全部"待人工"、信任度 0%，显示出来像坏了；改为结果页不展示复核，概念在架构页与代码中保留，单独向老师讲

### 3.5 Reasoner — LLM
- 审查叙述（专业报告）、冲突协调（成因+处置顺序）、规则生成
- 传输层 `requests` 直连本地 DeepSeek 代理（anthropic SDK 的 httpx 对代理返回 502，已绕过）

### 3.6 结果页 V2.1 + 上传页
- **结果页**：按角色化 Agent 组织（①QA → ②判定 → ④AI）、双栏（左判定列表带专业标签 / 右平面图）、**3D 等轴视图**（真实房间轮廓立体堆叠 + 楼层俯视）、专业筛选器、标准切换对比、HTML/Excel/PNG 导出
- **上传页**：去掉快速演示（审查必须真实 IFC）；上传后展示生成的 3D / 每层俯视 / 建筑剖面；参数编辑器 🟢模型/🟠默认 来源标注
- 卡片内联样式抽成 CSS class（`.card-title/.tag-disc-*/.tag-sev-*`），改一处 class 统一全部卡片

## 4. 数据与标准

### 测试 BIM 模型
| 模型 | 类型 | 规模 | 特点 |
|---|---|---|---|
| FZK Haus | 真实（ArchiCAD） | 2 层 / 7 房间 | 含空间边界（精确门关联），健康度 100 |
| **Office 3F** | 合成（自建） | 3 层 / 24 房间 | 办公楼，真实面积/门宽 0.9、QA 90，管线回归用 |
| Snowdon Towers | 真实 | 18 层 / 155 空间 / 132 门 | 无空间边界（几何兜底），健康度 80 |
| IfcOpenHouse | 真实 | 1 层结构壳 | 无房间，验证降级路径 |

**口径**：合成样例（Office 3F）测管线回归；真实样例（FZK/Snowdon）验真实感。

### 规范知识库（RAG）
- **免费核心全文**：Fire Code 2023、Approved Document v7.07、Code on Accessibility 2025、Buildability 2022、Environmental Sustainability 4th、Green Mark、Building Control Act / Fire Safety Act / 条例、**GB 55037（OCR）**、GB 55036
- **付费标准**：仅索引（标准号/名称/范围），不收全文（版权合规）——SS EN Eurocodes、SS 638/563/575/551/531/530、GB 50016/50974/51309/50116/50054/50055 等
- 物料清单：`scripts/rag_kb/kb_manifest.json`（36 份文档，免费/付费边界 + 已验证直链）

### 标准
CN GB ↔ SG FC23，**配置化扩展**（丢 `data/standards/<code>/` 文件夹即出现）。

## 5. 技术栈

| 层次 | 技术 |
|---|---|
| Web | Streamlit（多页、状态、动画） |
| BIM | ifcopenshell（解析/几何）+ networkx（疏散图） |
| 判定 | Python + JSON 规则引擎 |
| RAG | 本地语料 + pypdf/pymupdf/rapidocr（OCR） |
| LLM | DeepSeek（本地代理，`requests` 直连） |
| 报告 | Pillow（标注图）+ HTML |

## 6. 审查流水线

```
上传 IFC + 选标准
  → ① 模型可用性 QA（健康度 + 阻断）
  → ② 四专业逐层判定（消防/电气逐房间，结构逐构件，整楼聚合）
  → 冲突检测（同层同位置跨专业）
  → ④ LLM 审查叙述
  → 结果页：统计卡 + 双栏（判定列表 + 3D/俯视平面图）+ 专业筛选 + HTML/Excel 导出
```

## 7. 已知边界（如实）

1. **证据定位**：Reviewer 证据片段指向规范文本的标题/目录上下文，非具体条款（关键词检索的局限）
2. **解析速度**：Snowdon（142MB）解析 ~74s（几何曲面化代价，一次性）
3. **出口数偏高**：大房间（1150m²）出口数偏多（几何关联对共享墙双计，语义上两侧都算）
4. **启发式局限**：FZK 楼板占地=0（非矩形拉伸）、部分模型门宽靠名称/几何回退
5. **固定构造阈值**：STR-002 梁高公式 `max(0.2, min(span,6)/20)` 是工程近似（决策文档 `docs/STR002_rule_decision_request.md`），STR-003 板厚用静态 0.1m（混合板型更稳）
6. **付费标准无全文**：涉及付费标准（GB 500xx / SS 638 等）的判定，系统无法自动给出规范原文证据，需人工对照原文确认（复核显示已从结果页移除，概念单独讲）

## 8. 验证记录

- 引擎端到端：FZK / **Office 3F** / Snowdon / IfcOpenHouse 解析 + 四专业审查
- 红线预警：门宽 0.8m 违规、柱截面 0.101m 违规、梁/板真实数据判定
- 动态阈值：STR-002 主梁 0.24m 通过（阈值 0.204）、檩条 0.16m 报（阈值 0.30）
- AppTest 完整流程 0 异常（上传 FZK/Office 3F → 健康度 → 平面图 → 审查 → 结果页）
- 全部提交已推送 GitHub（`Radiant927/ArchCheck`）

## 9. 快速开始

```bash
cd ArchCheck
pip install -r requirements.txt
streamlit run app.py    # http://localhost:8501
# 上传 .ifc（如 bim/samples/FZK_Haus.ifc 或 office_3f.ifc），选标准，开始审查
```

关键脚本：
- `scripts/rag_kb/create_kb_structure.py` 生成知识库目录
- `scripts/rag_kb/ocr_pdf.py` 扫描 PDF → 可检索文本
- `scripts/rag_kb/cleaning_rules.py` 过期引用清洗
- `scripts/rag_kb/generate_rules_from_rag.py` 条文 → JSON 规则
- `scripts/generate_office_ifc.py` 生成 Office 3F 样例

## 10. 路线图

**已完成**：Agent ①-⑤ 全链路、四专业审查、动态阈值、标准配置化、RAG 知识库、**结果页 V2.1（双栏/3D 视图/筛选）**、数据诚实化（Unknown 类型/来源标注）、**Office 3F 样例**、去快速演示。

**待办/未来**：
- [ ] Reviewer 证据定位到具体条款（语义检索）
- [ ] Snowdon 解析提速（几何缓存/并发）
- [ ] 动态阈值推广到更多规则（需工程公式决策）
- [ ] 更多标准（ASEAN/EU）规则包
- [ ] 补更多真实样例（Duplex/Schependomlaan）
- [ ] 完整演示流程核对（office_3f + FZK）
