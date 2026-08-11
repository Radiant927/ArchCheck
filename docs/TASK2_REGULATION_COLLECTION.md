# Task 2 — 规范文档搜集交付记录（RAG 知识库）

> 课程任务 2「资料搜集与验证」前半：搜集新加坡 BCA/SCDF 与中国工程建设标准，构建 RAG 知识库。
> 日期：2026-08-11

---

## 1. 搜集成果总览

**数据源**：新加坡（BCA / SCDF / Singapore Statutes Online）+ 中国（住建部 / gov.cn 政策库）。

| 类别 | 文档 | 状态 |
|---|---|---|
| **免费核心（Priority 0，全文入库）** | Fire Code 2023、Approved Document v7.07、Code on Accessibility 2025、Environmental Sustainability 4th、CoP Buildability 2022、Green Mark GLS、Building Control Act、Fire Safety Act、Buildability & Productivity Regs、Environmental Sustainability Regs | ✅ 已下载 `data/rag_kb/SG_Free/` |
| | GB 55037-2022《建筑防火通用规范》 | ✅ 已下载 + **OCR**（扫描版转可检索文本） |
| | GB 55036-2022《消防设施通用规范》 | ✅ 已下载（自带文字层） |
| **付费标准（Priority 1，仅元数据索引）** | SS EN Eurocodes + NA、SS 638/563/575/551/531/530、GB 50016/50974/51309/50116/50054/50055/50010/50017/50011/50009 | ✅ 只登记标准号/名称/范围，**不收全文**（版权合规） |
| **已废弃（不入库）** | GB 50045（高层民用防火，已由 GB 50016 取代） | ✅ 标记剔除 |

完整 36 份清单见 `scripts/rag_kb/kb_manifest.json`。

## 2. 付费标准必要性分析

平台规则引擎的阈值全部硬编码在 JSON（`data/standards/`），判定**不读标准原文**；
免费 Fire Code + GB 55037/55036 已覆盖强制要求。因此：

> **没有任何付费标准是平台运行/演示所必需的。** 付费标准只用于增强 RAG 回答"具体条款细节"的深度；答不了时按既定口径降级为"请查阅原文"（数据合规设计）。

按"被规则引用 × 无免费替代"评估的优先级：

| 标准 | 引用规则 | 免费替代 | 建议 |
|---|---|---|---|
| **SS 638**（SG 电气） | EEE-002/003、BLD-003 | 无 | ⭐ 最值得（若加强 RAG）|
| **GB 50016**（CN 防火设计） | CIVIL-001~004、BLD-001 | GB 55037 覆盖强制部分，设计细节值在其内 | ⭐ 值得 |
| **SS 563**（SG 应急照明） | EEE-001、BLD-004 | Fire Code Ch.8 免费覆盖大部分 | 🟡 |
| **GB 50054 / GB 51309 / SS 575 / GB 50974 / GB 50055 / SS 531** | 少量 | 免费通用规范覆盖强制部分 | 🟢 低 |

**不需要**：结构类（SS EN 1990-1993、GB 50010/50017/50011/50009 —— 平台无结构规则）、SS 551（已不再引用）、GB 50116（未引用）、SS 530（未引用）。

**免费全文来源**：GB 55037/55036（住建部/gov.cn，`标准化法` 要求强制规范公开）与 Fire Code 2023（SCDF）为官方免费；GB 500xx / SS 系列**无官方免费全文**，网上非官方转载版权风险高，不建议用于合规演示。

## 3. RAG 就绪状态

| 文档 | 可检索文本 |
|---|---|
| GB 55037-2022 | ✅ 扫描版，已用 RapidOCR 转 `.txt`（`scripts/rag_kb/ocr_pdf.py`） |
| GB 55036-2022 | ✅ 自带文字层 |
| Fire Code 2023 / Approved Document 等 SG PDF | ✅ 自带文字层 |
| SG 法规（Act/Regs） | ✅ SSO 提取为 `.txt` |

清洗检查（`cleaning_rules.py --corpus`）对已入库文档 **0 错误**（无过期/错误引用）。

## 4. 复现

```bash
python scripts/rag_kb/create_kb_structure.py   # 生成目录结构
python scripts/rag_kb/ocr_pdf.py <扫描版.pdf>   # 扫描 PDF → 可检索 txt
python scripts/rag_kb/cleaning_rules.py --corpus data/rag_kb  # 入库前清洗
```
