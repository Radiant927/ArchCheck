# ArchCheck · Aicher 系统

**AI 多层建筑合规审查平台** — 智能体流水线 + 确定性规则引擎 + 3D 模型查看，支持中国 GB 与新加坡 FC23 双标准一键切换。

把一份建筑 BIM（IFC）模型丢进去，平台自动读取楼层 / 房间 / 构件 / 门宽 / 疏散距离，按所选规范做**消防、电气、结构、无障碍**四专业判定，跨楼层聚合并检测同层跨专业冲突，最后给出**带三维定位**的审查问题清单与可导出的报告。

> 每层单独看都合规、整栋累积却超限——这类问题人工审查最容易漏，正是平台要抓的。

## 核心特性

- **智能体流水线** — BIM Reader → 语义富化 → Compliance Judge → 三维查看 → 结果 → Reasoner（详见下方）
- **确定性规则引擎** — JSON 规则包，8 类算子 + 条件过滤 + 动态阈值，热更新无需改代码；**数值判定不交给 LLM**
- **双标准切换** — 🇨🇳 中国 GB / 🇸🇬 Singapore FC23，规则、阈值、条文引用一键切换，无需重启
- **IFC 读取 + 模型可用性 QA** — `ifcopenshell` 提取，单位 / 空间 / 几何 / 边界四查，输出健康度评分与致命门禁
- **3D 模型查看器** — 基于 `web-ifc` 的浏览器端三维查看（That Open Engine 前端），楼层过滤、视点切换、问题构件定位与高亮
- **语义富化 + 灰区仲裁** — LLM 只做归一词性（房型 / 材料 / 管道系统）；含糊规则交仲裁 Agent 出「AI 建议」，**待人工确认，绝不单独定案**
- **逐构件互检（crosscheck）** — 提取结果与真值逐件比对，量化几何 / 单位 / 匹配口径
- **预测性寿命预警** — 基于维保记录做生存分析（KM / Cox），输出风险排序检修清单；数据不足时**诚实弃权**（NotChecked），不编造
- **一键导出** — 标注图 / 修正图 PNG、统一 HTML 报告、Excel 结果表

## 快速开始

```bash
pip install -r requirements.txt
streamlit run app.py
# 平台 http://localhost:8501（同时自动在 :8765 起 3D 查看器静态服务）
```

侧边栏选标准（🇨🇳 GB / 🇸🇬 FC23）→ 上传 `.ifc`，或点演示模型直出结果。

**LLM 是可选的。** 判定、几何、报告全部确定性，不配 LLM 也能完整跑。需要叙述 / 仲裁 / 语义富化时，走本地代理，可用环境变量覆盖：`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`。

## 智能体流水线

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

**配套智能体：**

| 角色 | 职责 | 备注 |
|---|---|---|
| **KB Steward** | 规范知识库 RAG：检索条文、动态取值、规则生成 | 免费全文 + 付费索引策略 |
| **Reviewer** | 按 `code_ref` 检索规范原文复核每条判定 | 确定性检索，不拖慢主流程 |
| **Arbitrator** | 灰区规则仲裁，产出「AI 建议」待人工确认 | 必须引用条文证据，失败可降级 |

## 规则库

规则按标准分目录（`data/standards/<code>/`），JSON 格式，改文件即生效。

| 标准 | 消防 | 电气 | 全楼聚合 | 机电 | 结构 | 无障碍 | 合计 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 🇨🇳 中国 GB | 14 | 6 | 9 | 14 | 4 | 5 | **52** |
| 🇸🇬 Singapore FC23 | 13 | 6 | 9 | 13 | 4 | 5 | **50** |

支持算子：`<= >= > < == != in not_in`；规则可带条件过滤与 `dynamic_threshold`（公式 → RAG/LLM → 静态兜底）。

## 目录结构

```
ArchCheck/
├── app.py                  # Streamlit UI（上传 / 结果 / 架构 / 规范库）
├── core/                   # 平台内核
│   ├── config.py           # 路径 + Aicher 设计令牌
│   ├── i18n.py             # 中英双语字典
│   ├── engine.py           # 规则引擎：加载标准 / 跑规则 / 全楼审查 / 预测性审查
│   ├── drawing.py          # 平面图绘制 / 标注 / 修正 / 剖切
│   └── report.py           # HTML 报告生成
├── bim/                    # IFC 读取
│   ├── parser.py           # 门面：parse_ifc + QA
│   ├── extractor.py        # 提取楼层/房间/构件/门宽/疏散距离（单位自适应）
│   ├── qa_validator.py     # 模型可用性 QA：健康度 + 逐项检查
│   ├── samples/            # 6 个小样例
│   └── test-suites/        # 31 个真实/官方 IFC 测试模型
├── agents/                 # 智能体
│   ├── reviewer.py         # 规范原文复核
│   ├── enricher.py         # 语义富化（归一词性）
│   └── arbitrator.py       # 灰区仲裁
├── risk/                   # 预测性寿命预警（生存分析）
│   ├── families.py         # 构件族与协变量定义
│   ├── generator.py        # 合成维保数据（保留潜真值）
│   ├── survival.py         # KM / Cox + Breslow 基线预测
│   ├── adapter.py          # 审查数据 → 风险总体表
│   ├── evaluate.py         # 潜真值验证
│   └── csv_io.py           # 维保 CSV 读写与校验
├── kb/                     # 知识库
│   ├── semantic.py         # bge-m3 语义检索（免费语料）
│   └── steward.py          # 动态阈值：公式 → RAG/LLM → 兜底
├── llm/                    # DeepSeek 客户端（Anthropic 兼容本地代理）
├── web/                    # 3D 查看器前端
│   ├── serve.py            # 静态服务：/viewer 与 /ifc 临时文件
│   ├── viewer/             # web-ifc 三维查看页
│   └── viewer_bridge/      # Streamlit ↔ viewer 的 postMessage 桥
├── data/                   # 标准规则包 + 演示数据
├── scripts/                # 测评 / 互检 / 诊断 / 出图脚本
├── docs/                   # 文档（详见 docs/README.md）
├── presentation/           # 汇报材料（按日期）
└── output/                 # 运行产物（gitignored）
```

## 文档与测试模型

- 完整文档见 **[`docs/README.md`](docs/README.md)**（架构、规则格式、新增标准、方法边界）
- 测试模型：`bim/samples/`（6 个小样例，随仓库分发）+ `bim/test-suites/`（31 个真实 / 官方模型，用于读取完备性与规则激活测评）

## 方法边界（原型定位）

- **平面图**为代码生成的示意图纸，未接入 CV/OCR 识别真实图纸
- **建筑数据**以 IFC / JSON 驱动为主，非图像提取
- **跨楼层**指汇总量级判定，非三维空间连续推理
- **预测性预警**基于自有合成平台对潜真值验证，属前瞻性提示，**不代表现行违规**；数据不足时如实弃权

架构上，CV 图纸识别与更多数据源可作为「数据层」接入，不改动审查引擎内核。

## License

MIT — 详见 [LICENSE](LICENSE)。
