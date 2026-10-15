# ArchCheck 文档

AI 驱动的多层建筑合规审查平台。多智能体架构 + 确定性规则引擎 + 双标准（中国 GB / 新加坡 FC23）+ BIM/IFC 读取 + 3D 模型查看。

> 本文件是完整技术文档；项目主页与快速上手见根目录 [`README.md`](../README.md)。

---

## 1. 平台定位

ArchCheck 把建筑合规审查拆成两半，各司其职：

- **确定性判定**（几何、数值、阈值、跨楼层聚合）—— 交给 JSON 规则引擎，**可复算、可追溯、不依赖 LLM**
- **语义与叙述**（房型归类、灰区解释、审查叙述）—— 交给 LLM，但**只填枚举、不给数字、不单独定案**

核心痛点是**分层合规、整栋超限**：每层单独看都满足阈值，累计起来却突破消防 / 电气 / 排水要求。人工审查习惯逐层看，这个缺口最容易漏。

---

## 2. 智能体架构

```
上传 IFC（可选维保 CSV） + 选标准
        │
        ▼
① BIM Reader           解析 IFC → 楼层/房间/构件/门宽/疏散距离 · 模型可用性 QA（健康度 0-100）
        │
        ▼
   语义富化 Enricher     仅对含糊项归一词性：房型 / 材料 / 管道系统（LLM，只填枚举字段）
        │
        ▼
② Compliance Judge     确定性规则引擎：消防 / 电气 / 结构 / 无障碍
        │               跨楼层聚合 · 同层跨专业冲突检测 · 动态阈值
        ├──▶ ③ 三维模型    问题构件定位与高亮
        ├──▶ ④ 楼层平面图  标注图 / 修正图
        └──▶ ⑤ 审查问题    已复核 ✅ / 待人工复核 ⚠️ / 未检查（数据缺失如实上报）
        │
        ▼
⑥ Reasoner             LLM 综述：专业叙述 · 跨专业冲突成因 · 协同处置顺序
```

| 智能体 | 职责 | 实现 |
|---|---|---|
| **BIM Reader** | 解析 IFC + 模型可用性 QA | `bim/parser.py`, `extractor.py`, `qa_validator.py` |
| **Enricher** | 语义富化：房型 / 材料 / 管道系统归一词性 | `agents/enricher.py` |
| **Compliance Judge** | 四专业确定性判定、跨楼层聚合、冲突检测 | `core/engine.py` |
| **KB Steward** | 规范知识库 RAG：条文检索、动态阈值、规则生成 | `kb/semantic.py`, `steward.py` |
| **Reviewer** | 按 `code_ref` 复核每条判定，标注证据 | `agents/reviewer.py` |
| **Arbitrator** | 灰区规则仲裁 → 「AI 建议」待人工确认 | `agents/arbitrator.py` |
| **Reasoner** | LLM 综述与协同处置建议 | `llm/client.py` |

工程约定：
- **LLM 不碰数字** —— 语义富化只填受控词表字段；判定全部走规则引擎
- **仲裁不单独定案** —— 每条结果均为 `pending` 的人工建议，必须引用条文证据
- **失败可降级** —— LLM / RAG 不可用时，主流程照常出结果，绝不阻塞

---

## 3. 快速开始

```bash
pip install -r requirements.txt
streamlit run app.py
# 平台 http://localhost:8501（同时自动在 :8765 起 3D 查看器静态服务）
```

侧边栏切换标准（🇨🇳 GB / 🇸🇬 FC23）→ 上传 `.ifc` 或点演示模型。LLM 可选，环境变量覆盖：`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`。

维保 / 监测 CSV（可选，启用寿命预测）：上传 IFC 后可继续上传 `pipe_service.csv`、`maintenance_log.csv`、`pipe_monitoring.csv`；不上传则相关规则保持 NotChecked。

---

## 4. 项目结构

```
ArchCheck/
├── app.py                     # Streamlit UI（上传与审查 / 审查结果 / 平台架构 / 规范库）
├── core/
│   ├── config.py              # 路径（HERE/OUTPUT/DATA）+ Aicher 设计令牌
│   ├── i18n.py                # 中英双语字典、T / LANG
│   ├── engine.py              # 规则引擎：load_standard / run_rules / run_full_review / 预测性审查
│   ├── drawing.py             # 平面图绘制 / 标注 / 修正 / 剖切
│   └── report.py              # HTML 报告生成
├── bim/
│   ├── parser.py              # 门面：parse_ifc（提取 + QA 一次完成）
│   ├── extractor.py           # IFC → 结构 + 审查数据（单位自适应）
│   ├── qa_validator.py        # 模型可用性 QA：健康度 + 逐项检查（致命门禁）
│   ├── samples/               # 6 个小样例（随仓库分发）
│   └── test-suites/           # 31 个真实/官方 IFC 测试模型
├── agents/
│   ├── reviewer.py            # Reviewer：条文复核
│   ├── enricher.py            # Enricher：语义富化
│   └── arbitrator.py          # Arbitrator：灰区仲裁
├── risk/                      # 预测性寿命预警（独立于审查引擎）
│   ├── families.py            # 构件族与协变量定义
│   ├── generator.py           # 合成维保数据（保留潜真值 t_true）
│   ├── survival.py            # KM / Cox(PHReg) + Breslow 基线预测
│   ├── adapter.py             # 审查数据 bdata → 风险总体表
│   ├── evaluate.py            # 潜真值验证
│   └── csv_io.py              # 维保 CSV 读写与校验
├── kb/
│   ├── semantic.py            # bge-m3 语义检索（免费语料，可降级为空）
│   └── steward.py             # 动态阈值：公式 → RAG/LLM → 静态兜底
├── llm/
│   └── client.py              # DeepSeek 客户端（Anthropic 兼容本地代理）
├── web/
│   ├── serve.py               # 静态服务：/viewer 与 /ifc 临时文件（独立后台 HTTP）
│   ├── viewer/                # web-ifc 三维查看页
│   └── viewer_bridge/         # Streamlit ↔ viewer 的 postMessage 桥
├── data/
│   ├── demo_building_data.json
│   └── standards/{cn,sg}/     # 规则包（见 §5）
├── scripts/                   # 测评 / 互检 / 诊断 / 出图脚本
├── docs/                      # 本文档
├── presentation/              # 汇报材料（按日期）
└── output/                    # 运行产物（gitignored）
```

---

## 5. 规则引擎

规则以 JSON 存储、按标准分目录，改文件即生效（热更新，无需改代码）。一条典型规则：

```json
{
    "id": "BLD-001",
    "name": "首层疏散外门总净宽检查",
    "description": "首层疏散外门总净宽应按最多一层人数计算满足最小要求",
    "field": "ground_floor_exit_width_m",
    "operator": ">=",
    "threshold": 3.0,
    "unit": "m",
    "severity": "High",
    "code_ref": "GB 50016",
    "message": "首层疏散外门总净宽 {value}m 小于要求 {threshold}m，需加宽首层外门。"
}
```

- **算子**：`<=` `>=` `>` `<` `==` `!=` `in` `not_in`
- **条件过滤**：可选 `condition_field` / `condition_operator` / `condition_threshold`，仅当前置字段满足时才评估该规则
- **动态阈值**：可选 `dynamic_threshold` 块，取值顺序为 公式 → RAG/LLM → 静态兜底（`kb/steward.py`，按 `(rule_id, context)` 缓存）
- **数据缺失如实上报**：当判定所需字段在模型中缺失时，规则计为「未检查 / NotChecked」，而非默认通过

---

## 6. 标准与规则库

| 标准 | 消防 | 电气 | 全楼聚合 | 机电 | 结构 | 无障碍 | 合计 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 🇨🇳 中国 GB | 14 | 6 | 9 | 14 | 4 | 5 | **52** |
| 🇸🇬 Singapore FC23 | 13 | 6 | 9 | 13 | 4 | 5 | **50** |

- 中国：GB 50016《建筑设计防火规范》、GB 51309 / GB 50054 / GB 50055
- 新加坡：Singapore Fire Code 2023、SS 638 / SS 563 / SS 531

---

## 7. BIM 读取与模型 QA

`bim/parser.parse_ifc()` 一次完成「提取 + 质检」：

- **提取**（`extractor.py`）：楼层、房间（几何求面积）、构件分类计数、门宽、疏散距离、MEP 管道（端口/系统/配件/材料）、杆件拓扑；长度单位从 IFC 读取并自适应缩放
- **QA**（`qa_validator.py`）：单位 / 空间 / 几何 / 边界四查，输出健康度评分与逐项报告；致命项（空壳、关键构件无几何）应拦在审查之前
- QA 消息中英双语存储（解析时一次生成，之后可切 UI 语言）

---

## 8. 3D 查看器

- 前端 `web/viewer/` 基于 `web-ifc`（That Open Engine）在浏览器内加载 IFC，支持楼层过滤、视点切换、问题构件定位与高亮、房间导航
- `web/serve.py` 起一个独立后台 HTTP 服务：`/viewer/*` 静态前端，`/ifc/<token>/*` 会话临时模型文件，`/api/*` 问题数据
- Streamlit 与 viewer 通过 `web/viewer_bridge/` 的 `postMessage` 桥通信（点击构件 → 回传 Python）

---

## 9. 预测性寿命预警（生存分析）

`risk/` 是独立模块，**不改动审查引擎与查看器**：

- **数据流**：`adapter.py` 把审查数据（管道台账 + 维保日志 + 监测读数）组装成风险总体表；无维保数据时如实报告「不可用」
- **建模**：`survival.py` 提供 Kaplan-Meier 与 Cox 比例风险（statsmodels `PHReg`），并用 Breslow 基线做个体预测
- **验证**：`generator.py` 生成合成维保数据并**保留潜真值**，`evaluate.py` 用潜真值打分（而非删失观测）
- **接入引擎**：`core/engine.py:run_predictive_review()` 输出风险排序检修清单；数据不足 / 未收敛 / 监测体制不一致时**诚实弃权**，绝不编造预测
- 预测属**前瞻性提示**，不代表现行违规

---

## 10. 语义富化与仲裁

- **Enricher**（`agents/enricher.py`）：判定**之前**运行，只对确定性分类器含糊的项调用 LLM，从受控词表填 `room.type` / `element.material_class` / `pipe.pipe_type`；高置信关键词命中不经过 LLM；结果缓存 + 降级
- **Arbitrator**（`agents/arbitrator.py`）：仅对规则中带 `arbitration` 块的灰区规则介入，产出 `pending` 的「AI 建议」，附条文证据，交人工确认

---

## 11. 测试模型与测评

- `bim/samples/`：6 个小样例（FZK-Haus、IfcOpenHouse、office_3f、topology_chain、Duplex-MEP、Schependomlaan），随仓库分发
- `bim/test-suites/`：31 个真实 / 官方 IFC 模型，按 `real-project/`、`official/`、`mep/` 分组，用于读取完备性、几何精度、规则激活测评
- 测评与诊断脚本（`scripts/`）：`benchmark_ifc.py`（读取完备性 6 维）、`crosscheck_ifc.py`（逐构件互检）、`run_full_benchmark.py`、`diagnose_*.py`

---

## 12. 新增一个标准

新增标准是**纯配置**改动 —— 放一个目录，侧边栏自动出现（扫描 `data/standards/`）：

1. 建 `data/standards/<code>/meta.json`：`id`、`name`、`short_name`、`category`、`flag`、`language`、`civil_codes`、`eee_codes`
2. 加入共享 schema 的规则包：`civil_rules.json`、`eee_rules.json`、`building_rules.json`，以及可选的 `structural_rules.json`、`mep_rules.json`、`accessibility_rules.json`
3. 规则可加 `dynamic_threshold` 块（公式 → RAG/LLM → 兜底）

无需改动引擎或 `app.py`。

---

## 13. 方法边界（原型定位）

- 平面图为**代码生成的示意图纸**，未接入 CV/OCR 识别真实图纸
- 建筑数据以 **IFC / JSON 驱动**为主，非图像提取
- **跨楼层**指汇总量级判定，非三维空间连续推理
- **预测性预警**基于自有合成平台对潜真值验证，属前瞻性提示，不代表现行违规

架构上，CV 图纸识别与更多数据源可作为「数据层」接入，不改动审查引擎内核。

---

## 14. License

MIT — 详见仓库根目录 [LICENSE](../LICENSE)。
