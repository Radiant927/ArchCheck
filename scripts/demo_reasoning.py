#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公寓模型 + 知识库推理演示（8-26 会议任务 2）。

完整链路：提问 → 语义检索(kb.semantic) → 条文证据(带置信度+词法确认)
        → 规则引擎判定(跑在公寓模型上) → 结果。

公寓模型用 Schependomlaan（完整住宅，6 层），FZK Haus 作补充。

用法:
  python scripts/demo_reasoning.py            # 默认 CN 标准 + Schependomlaan
  python scripts/demo_reasoning.py --std sg   # 新加坡标准
  python scripts/demo_reasoning.py --model FZK_Haus   # 换住宅样例
"""
import argparse
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bim.parser import parse_ifc
from bim.extractor import build_review_data
from core import engine
from kb import semantic

# 演示场景：自然语言问题 -> 对应规则 -> 一句口头解释
# 全部用 GB 55037（在免费知识库里，语义检索能命中真条文）。
# 场景 4/5 故意选覆盖类规则，演示「空作用域未检查」和「缺字段未检查」两种诚实上报。
SCENARIOS = [
    {
        "question": "公共建筑的疏散门净宽最小不能小于多少？",
        "rule_id": "CIVIL-004",
        "intro": "【场景 1】疏散门净宽 —— 从「门够不够宽」看疏散安全",
    },
    {
        "question": "疏散走道的疏散距离最长不能超过多少？",
        "rule_id": "CIVIL-001",
        "intro": "【场景 2】疏散距离 —— 逃生路线不能太长",
    },
    {
        "question": "一个房间至少要设置几个疏散出口？",
        "rule_id": "CIVIL-003",
        "intro": "【场景 3】疏散出口数量 —— 人多了要有多个出口",
    },
    {
        "question": "楼梯间和走廊这些疏散路径，一定要设应急照明吗？",
        "rule_id": "EEE-001",
        "intro": "【场景 4】应急照明 —— 演示「模型无电气设备 → 规则未检查」",
    },
    {
        "question": "室内消火栓的布置间距最大是多大？",
        "rule_id": "MEP-009",
        "intro": "【场景 5】消火栓间距 —— 演示「规则在库但模型缺字段 → 未检查」",
    },
]


def evidence_lines(question, top_k=2):
    """语义检索命中的条文证据（带分数 + 词法确认）。"""
    hits = semantic.search(question, top_k=top_k)
    if not hits:
        return ["（语义索引不可用，跳过证据）"]
    out = []
    for chunk, score in hits:
        ok = "✓词法确认" if semantic.accept(question, chunk, score) else "△仅语义"
        out.append(f"  [{score:.3f} {ok}] {chunk['doc']}: "
                   f"{chunk['text'][:80].replace(chr(10), ' ')}…")
    return out


def rule_outcome(res, rule_id, title):
    """该规则在这份审查结果里的判定结果（违规/数据缺失/未检查/通过）。"""
    hits = [i for i in res["all_issues"] if i.get("rule_id") == rule_id]
    # 先按 rule_id 匹配覆盖；再匹配"空作用域聚合"覆盖（按规则名出现在描述里）
    cov = [c for c in res["coverage_findings"] if c.get("rule_id") == rule_id]
    if not cov:
        cov = [c for c in res["coverage_findings"]
               if c.get("rule_id", "").startswith("scope::") and title in c.get("description", "")]
    if hits:
        lines = [f"  ✗ 违规 {len(hits)} 处（{title}）："]
        for h in hits[:3]:
            sev = h.get("severity", "")
            lines.append(f"     - [{sev}] {h.get('location','-')}: {h['description'][:70]}")
        if len(hits) > 3:
            lines.append(f"     … 共 {len(hits)} 处")
        return "\n".join(lines)
    if cov:
        return f"  ⚠ 未检查：{cov[0]['description'][:90]}"
    return f"  ✓ 全部通过（{title} 无发现）"


def run_demo(std_id="cn", model_name="Schependomlaan"):
    print("=" * 72)
    print(f"公寓模型 + 知识库推理演示 · 标准 {std_id.upper()} · 模型 {model_name}")
    print("=" * 72)

    # 1) 一次性加载模型审查结果（避免每条场景重复解析大模型）
    path = ROOT / "bim" / "samples" / f"{model_name}.ifc"
    print(f"\n[加载模型] {path.name} …")
    bdata = build_review_data(parse_ifc(path))
    res = engine.run_review_with_standard(std_id, bdata)
    rules = {r["id"]: r for std in (engine.load_standard(std_id),)
             for r in std["civil"] + std["eee"] + std["structural"] + std["mep"]
             + std["building"] + std["accessibility"]}
    print(f"[模型就绪] 房间 {sum(len(f.get('rooms', [])) for f in bdata['floors'])} 个，"
          f"层 {len(bdata.get('floors', []))} 层，违规 {len(res['all_issues'])} 条")

    print("\n" + "=" * 72)
    print("演示链路：提问 → 语义检索 → 条文证据 → 规则判定 → 结果")
    print("=" * 72)

    for sc in SCENARIOS:
        print(f"\n{sc['intro']}")
        print(f"  ❓ 提问：{sc['question']}")
        print("  🕮 语义检索命中的条文（证据）：")
        for ln in evidence_lines(sc["question"]):
            print(ln)
        rule = rules.get(sc["rule_id"])
        if rule:
            print(f"  ⚖ 命中规则：{rule['name']}（{rule.get('code_ref','')}）"
                  f"[阈值 {rule.get('threshold','-')} {rule.get('unit','')}]")
        print("  判定结果（在公寓模型上）：")
        print(rule_outcome(res, sc["rule_id"], rule["name"] if rule else sc["rule_id"]))
    return 0


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--std", default="cn", choices=["cn", "sg"])
    ap.add_argument("--model", default="Schependomlaan",
                    choices=["Schependomlaan", "FZK_Haus", "office_3f"])
    args = ap.parse_args()
    return run_demo(args.std, args.model)


if __name__ == "__main__":
    sys.exit(main())
