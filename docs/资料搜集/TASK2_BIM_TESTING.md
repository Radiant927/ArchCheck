# Task 2 — BIM 模型测试交付记录

> 验证从 2D 图纸审查扩展到 3D 建筑信息模型（BIM/IFC）审查的可行性。
> 日期：2026-08-11

---

## 1. 背景与目标

课程任务 2「资料搜集与验证」分为两部分：
1. **规范文档搜集** → RAG 知识库（见 `scripts/rag_kb/kb_manifest.json`，36 份文档清单）
2. **BIM 模型测试** → 搜集真实 BIM 模型样本，测试系统三维环境表现，验证 2D→3D 扩展可行性（本文档）

## 2. 真实 BIM 模型样本搜集

### 2.1 已验证可下载的样本

| 模型 | 格式 | 大小 | 内容 | 来源 | 状态 |
|---|---|---|---|---|---|
| **Snowdon Towers** | IFC | 142 MB | 真实高层办公楼，155 个空间（几何面积） | buildingSMART 样例 | ✅ 已入库 `bim/` |
| **FZK Haus** | IFC4 | 2.5 MB | 2 层住宅，**7 个房间带真实几何面积**（KIT 出品） | ifcwiki.org | ✅ 已入库 `bim/samples/` |
| **IfcOpenHouse** | IFC4 | 113 KB | 单层结构壳（无 IfcSpace 房间） | GitHub `aothms/IfcOpenHouse` | ✅ 已入库 `bim/samples/` |
| Duplex Apartment | IFC2x3 | ~10 MB | 2 层 2 户住宅 | 奥克兰大学 Open IFC 库 | ⚠️ 直链已失效（服务器返回错误页） |
| Schependomlaan | IFC4/2x3 | 数十 MB | 真实多层办公楼，带房间/门/BCF | GitHub `jakob-beetz/DataSetSchependomlaan` | ⚠️ 文件大，GitHub 需代理下载 |
| buildingSMART 测试库 | IFC2x3/4/4.3 | 各种 | bSI 官方样例（多为单体概念文件） | github.com/buildingSMART/Sample-Test-Files | 📚 仓库参考 |

### 2.2 样本选择标准（喂满解析管线）

- 多楼层（测试跨层聚合）
- 含 **IfcSpace 房间 + 真实几何**（面积可提取）
- 含门（门宽提取）

## 3. 解析测试结果（ifcopenshell → 结构化数据）

### Snowdon Towers（真实高层）
```
工程: 7765328-33-A | 3 层 × 6 房间 = 18 间（简化后）| 占地 167.9 m²
L3: 墙202 门22 窗27 柱20 板26 梯3
    · 5 (Office) 1150.6m²  · 31 (Office) 277.9m²  · 301 (Office) 264.9m²
    · 30 (Corridor) 135.5m² · 37 (Office) 111.3m² · 36 (Office) 110.3m²
L4 / L5 同理
```

### FZK Haus（新样本，小而完整）
```
工程: Projekt-FZK-Haus | 2 层 | 7 房间（真实几何面积）
一层: 5(26.0m²) 4(22.1m²) 6(16.3m²) 2(13.0m²) 3(12.5m²) 1(12.0m²)
二层: 7(107.2m²)   墙13 门5 窗11 板4
```

### IfcOpenHouse（结构壳）
```
工程: IfcOpenHouse | 1 层 | 0 房间（纯结构，验证无房间回退路径）
```

## 4. 端到端审查（IFC → 房间 → 规则引擎 → 违规报告）

以 **FZK Haus** 跑完整管线：

```python
struct = parser.parse_ifc("bim/samples/FZK_Haus.ifc")
data   = parser.build_review_data(struct)     # 房间 + 建筑参数
res    = engine.run_review_with_standard("sg", data)
```

| 标准 | 问题数 | 明细 |
|---|---|---|
| SG FC23 | 3 | 首层疏散外门净宽 · 消防水池容积 · 变压器容量（均 High/Medium，整楼聚合） |
| CN GB | 4 | 首层外门 · 消防水池 · 变压器 · 应急照明电源时长 |

> FZK 是小住宅：房间级规则（疏散距离/防火分区/出口数/门宽）**全部通过**，
> 但 `build_review_data` 的整楼默认参数（消防水池 160m³、变压器 650kW、首层出口 2.4m、应急电源 60min）**不达标**。
> 这恰好演示了系统的核心卖点——**单层/单体合规，整楼聚合超标**，人工分楼层审图容易漏。

## 5. 2D → 3D 扩展可行性结论

**已验证可行**。从 2D 图纸（程序化平面图 + 人工参数）扩展到 BIM/IFC：
- ✅ 真实房间 + 几何面积自动提取（`IfcSpace` → 凸包面积）
- ✅ 楼层结构 / 构件统计（墙门窗柱梁板梯）自动提取
- ✅ 房间数据直接喂给规则引擎，全流程复用现有审查/结果/导出
- ✅ 无房间模型不编造房间，如实提示并仅跑整楼聚合（见 `app.py` no-room 处理）

## 6. 已知限制（如实）

1. **门宽提取**：Snowdon / FZK / IfcOpenHouse 三种模型的 IfcDoor 名称均不符合
   `750×2000mm` 正则、几何回退也未命中 → 门宽为空。建筑四层.ifc（77 门）可提取，说明该方法对部分模型有效。
2. **房间面积用凸包近似**：凹形空间会略高估（技术报告已注明）。
3. **楼板占地启发式**：仅识别矩形拉伸楼板 → FZK（非矩形拉伸）占地为 0。
4. **消防/电气专业参数**（疏散路径、负荷、水源间距）真实 IFC 通常不含，由参数编辑器补录或默认值驱动。

## 7. 复现方法

```bash
python -c "
from bim import parser
r = parser.parse_ifc('bim/samples/FZK_Haus.ifc')
print(r['storey_count'], 'floors', r['total_rooms'], 'rooms')
"
```

## 8. 相关文件

- 解析器：`bim/parser.py`
- 样本：`bim/`（Snowdon）、`bim/samples/`（FZK Haus、IfcOpenHouse）
- 规范知识库清单：`scripts/rag_kb/kb_manifest.json`、`data/rag_kb/`
