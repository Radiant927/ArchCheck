# -*- coding: utf-8 -*-
"""条文 → 机器规则 生成工具（台阶⑤ · 规则平台化）。

把一段规范条文交给 LLM（DeepSeek）转成引擎可用的 JSON 规则，
打印供人工确认，可追加到 data/standards/<std>/<category>_rules.json。

用法:
  python scripts/rag_kb/generate_rule_from_clause.py "疏散走道的净宽度不应小于1.1m" --std cn --category civil --apply
"""
import argparse
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from llm.client import generate_rules_from_code  # noqa: E402


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("clause", help="规范条文文本")
    ap.add_argument("--std", default="cn", help="标准 id（cn / sg）")
    ap.add_argument("--category", default="civil", help="规则类别（civil/eee/building/structural/mep）")
    ap.add_argument("--apply", action="store_true", help="确认后追加到规则文件")
    args = ap.parse_args()

    print(f"条文: {args.clause}\n生成中...")
    rules = generate_rules_from_code(args.clause, std_id=args.std, category=args.category)
    if not rules:
        print("生成失败（LLM 未返回有效 JSON）。")
        return 1

    print("\n=== 生成的规则 ===")
    print(json.dumps(rules, ensure_ascii=False, indent=2))

    if args.apply:
        path = ROOT / "data" / "standards" / args.std / f"{args.category}_rules.json"
        existing = json.load(open(path, encoding="utf-8")) if path.exists() else []
        ids = {r.get("id") for r in existing}
        new = [r for r in rules if r.get("id") not in ids]
        existing.extend(new)
        json.dump(existing, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\n已追加 {len(new)} 条到 {path}（现有 {len(existing)} 条）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
