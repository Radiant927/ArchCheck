# -*- coding: utf-8 -*-
"""语义检索演示 CLI：查一条 → 语义 top-3 + 旧关键词对比.

用法:  python scripts/rag_kb/search_semantic.py "走廊疏散距离"
        python scripts/rag_kb/search_semantic.py           # 交互模式
"""
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from agents.reviewer import _kb_txts
from kb import semantic


def kw_result(q):
    pat = re.escape(q[:6])
    hits = []
    for fname, text in _kb_txts():
        if re.search(pat, text):
            hits.append(fname)
    return hits


def show(q):
    print(f"\n查询: {q}")
    print("-" * 78)
    kw = kw_result(q)
    print(f"[旧·关键词] 子串命中: {(' | '.join(kw) if kw else '无（换种说法就搜不到）')}")
    res = semantic.search(q, top_k=3)
    if not res:
        print("[语义] 无结果")
        return
    for i, (c, s) in enumerate(res, 1):
        acc = "✓接受" if semantic.accept(q, c, s) else "✗低置信(判manual)"
        txt = c["text"][:110].replace("\n", " ")
        print(f"[语义#{i}] {s:.3f} {acc} | {c['doc'][:26]}")
        print(f"         {txt}")


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    if len(sys.argv) > 1:
        show(" ".join(sys.argv[1:]))
        return
    print("交互模式：输入查询回车（q 退出）")
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or q.lower() == "q":
            break
        show(q)


if __name__ == "__main__":
    main()
