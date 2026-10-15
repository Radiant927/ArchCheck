# 基线测试代码（存档副本）

本目录是 2026-09-08 基线测试所用脚本的**存档副本**，供汇报/归档查看。

> 运行提示：这些脚本依赖仓库里的 `bim/`（IFC 解析）和 `core/`（规则引擎）包，
> 因此**实际运行需回到 ArchCheck 仓库原路径**（`scripts/` 目录），本目录副本仅作展示。

## 脚本与作用

| 文件 | 作用 |
|---|---|
| `benchmark_ifc.py` | 单文件六轴打分（健壮 A / 提取 B / 字段 C / 准确性 D / 规则激活 E / 性能 F），D 轴已修为按模型实际数据测各专业尺寸 |
| `run_full_benchmark.py` | 批量跑整个测试集，汇总 CSV + 每模型 JSON（批量入口）|
| `analyze_benchmark.py` | 把批量结果汇总为三层得分，并生成 Q4 跨版本、P3 跨软件对比 |
| `diagnose_rule_activation.py` | 逐条规则统计激活率，找"沉睡"规则及跳过原因 |
| `diagnose_entity_coverage.py` | 列"模型里有但提取器没读"的实体类型（覆盖缺口）|
| `diagnose_geometry_accuracy.py` | 几何尺寸合理性 / 单位对照诊断 |

## 运行命令（在仓库根目录执行）

```bash
# 1) 批量跑测试集（输出到 output/benchmark_xxx/）
python scripts/run_full_benchmark.py bim/test-suites --out output/benchmark_0908_final

# 2) 汇总三层 + 跨版本/跨软件对比
python scripts/analyze_benchmark.py output/benchmark_0908_final/all_reports.json \
    --out output/benchmark_0908_final

# 3) 诊断（按需）
python scripts/diagnose_rule_activation.py bim/test-suites --out output/benchmark_0908_final
python scripts/diagnose_entity_coverage.py bim/test-suites --out output/benchmark_0908_final
python scripts/diagnose_geometry_accuracy.py bim/test-suites --out output/benchmark_0908_final
```

## 数据文件位置

- 测试 IFC：`presentation/2026-09-08/test-suites/`（31 个）
- 基准测试结果：仓库 `output/benchmark_0908/`（改进前）、`output/benchmark_0908_final/`（改进后最终）
- 汇总报告：仓库 `docs/规划与技术/实用性测试报告与改进计划_2026-09-08.md`
