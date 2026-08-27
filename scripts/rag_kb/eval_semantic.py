# -*- coding: utf-8 -*-
"""语义检索 量化评估 v2 —— 条文(chunk)级 + 文档级 + 守卫 + 关键词基线.

升级点（对照 2026-08-25 评审意见）：
1. 金标准扩至 63 条（55 正 + 8 负），区分 easy/medium/hard 难度；
2. 标注粒度从「文档级」升级为「chunk 条文级」：target_phrases 定位具体条文；
3. 新增 Recall@3 / F1；
4. 负样本区分 fully_out（完全语料外）与 partial_overlap（部分重叠边界）；
5. 关键词基线改为同语料同切分的 BM25（单一变量对比）；
6. 评测前校验 target_phrases 是否真实存在于语料（防止金标准悬空）。

用法:  python scripts/rag_kb/eval_semantic.py
"""
import io
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from kb import semantic  # noqa: E402

GS = ROOT / "data" / "rag_kb" / "_semantic" / "gold_standard.json"
INDEX = ROOT / "data" / "rag_kb" / "_semantic"


# --------------------------------------------------------------------------
# BM25 关键词基线（同一 chunk 语料，同一 tokenization）
# --------------------------------------------------------------------------
def _tokens(s):
    toks = [w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in semantic._EN_STOP]
    cjk = re.findall(r"[一-鿿]", s)
    toks += ["".join(b) for b in zip(cjk, cjk[1:])]
    return toks


_WS = re.compile(r"\s+")


def _norm(s):
    """Strip whitespace AND punctuation — chunk text carries OCR spaces and
    smart quotes (e.g. “builder's licence”) that break literal matching."""
    t = _WS.sub("", s)
    return re.sub(r"[^0-9A-Za-z一-鿿]", "", t)


class BM25:
    """Same-corpus BM25 keyword baseline (k1=1.5, b=0.75)."""

    def __init__(self, docs):
        self.doc_toks = [_tokens(d) for d in docs]
        n = len(docs)
        df = Counter()
        for t in self.doc_toks:
            df.update(set(t))
        self.avgdl = sum(len(t) for t in self.doc_toks) / max(n, 1)
        self.idf = {w: math.log((n - c + 0.5) / (c + 0.5) + 1) for w, c in df.items()}
        self.n = n

    def score(self, q, i):
        qt = _tokens(q)
        dl = len(self.doc_toks[i])
        tf = Counter(self.doc_toks[i])
        s = 0.0
        for w in set(qt):
            if w not in self.idf:
                continue
            f = tf.get(w, 0)
            denom = f + 1.5 * (1 - 0.75 + 0.75 * dl / max(self.avgdl, 1e-6))
            s += self.idf[w] * f * (1.5 + 1) / max(denom, 1e-6)
        return s

    def search(self, q, top_k=3):
        scored = sorted(range(self.n), key=lambda i: -self.score(q, i))[:top_k]
        return scored


# --------------------------------------------------------------------------
# 加载语料与金标准
# --------------------------------------------------------------------------
def load_chunks():
    with open(INDEX / "chunks.json", encoding="utf-8") as f:
        return json.load(f)


def validate_gold(chunks, gs):
    texts = [_norm(c["text"]) for c in chunks]
    problems = []
    for g in gs:
        if not g["expect_hit"]:
            continue
        for ph in g["target_phrases"]:
            if not any(_norm(ph) in t for t in texts):
                problems.append(f"[{g['topic']}] 目标短语未命中任何 chunk: {ph[:60]}")
    return problems


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    gs = json.load(open(GS, encoding="utf-8"))
    chunks = load_chunks()
    pos = [g for g in gs if g["expect_hit"]]
    neg = [g for g in gs if not g["expect_hit"]]

    problems = validate_gold(chunks, gs)
    if problems:
        print("⚠️  金标准悬空校验:")
        for p in problems:
            print("   ", p)
    else:
        print("✅ 金标准校验: 全部 target_phrases 均在语料中存在\n")

    bm = BM25([c["text"] for c in chunks])

    stat = dict(doc1=0, doc3=0, chunk1=0, chunk3=0, recall3=0,
                chunk1_guard=0, bm25_1=0, bm25_3=0,
                false_reject=0, cross_relevant=0, cross_found=0)

    def hit_doc(g, c):
        return g["expected_doc"] in c["doc"]

    def hit_chunk(g, c):
        nt = _norm(c["text"])
        return any(_norm(ph) in nt for ph in g["target_phrases"])

    print("=== 逐条（chunk 级 top-3）===")
    for g in pos:
        res = semantic.search(g["query"], top_k=3)
        top = res[:3] if res else []
        d1 = top and hit_doc(g, top[0][0])
        d3 = any(hit_doc(g, c) for c, _ in top)
        c1 = top and hit_chunk(g, top[0][0])
        c3 = any(hit_chunk(g, c) for c, _ in top)
        g1 = False
        if top:
            chunk, score = top[0]
            g1 = semantic.accept(g["query"], chunk, score) and hit_chunk(g, chunk)
        if g["cross_doc"]:
            stat["cross_relevant"] += len(g["target_phrases"])
            for ph in g["target_phrases"]:
                if any(ph in c["text"] for c, _ in top):
                    stat["cross_found"] += 1
        if c1 and top and not semantic.accept(g["query"], top[0][0], top[0][1]):
            stat["false_reject"] += 1
        bm_top = bm.search(g["query"], 3)
        bm1 = bm_top and any(hit_chunk(g, chunks[i]) for i in bm_top[:1])
        bm3 = any(hit_chunk(g, chunks[i]) for i in bm_top)
        stat["bm25_1"] += bm1
        stat["bm25_3"] += bm3

        stat["doc1"] += d1
        stat["doc3"] += d3
        stat["chunk1"] += c1
        stat["chunk3"] += c3
        stat["chunk1_guard"] += g1
        if c3:
            stat["recall3"] += 1
        tag = "OK" if c3 else ("DOC" if d3 else "MISS")
        first = top[0][0]["text"][:22].replace("\n", " ") if top else "(无)"
        print(f"[{tag:4s}][{g['difficulty']:6s}] {g['topic']:16s} "
              f"doc@1={str(d1)[0]} doc@3={str(d3)[0]} chunk@1={str(c1)[0]} "
              f"chunk@3={str(c3)[0]} bm25@1={str(bm1)[0]} | {first}")

    n = len(pos)
    print("\n=== 量化结果（55 条期望命中）===")
    print("--- 文档级（旧粒度，对照）---")
    print(f"Doc P@1 : {stat['doc1']}/{n} = {stat['doc1']/n:.0%}")
    print(f"Doc P@3 : {stat['doc3']}/{n} = {stat['doc3']/n:.0%}")
    print("\n--- 条文级 chunk（新粒度）---")
    print(f"Chunk P@1 : {stat['chunk1']}/{n} = {stat['chunk1']/n:.0%}")
    print(f"Chunk P@3 : {stat['chunk3']}/{n} = {stat['chunk3']/n:.0%}")
    print(f"Chunk R@3 : {stat['recall3']}/{n} = {stat['recall3']/n:.0%}")
    f1 = 2 * (stat['chunk1'] / n) * (stat['recall3'] / n) / max((stat['chunk1'] / n + stat['recall3'] / n), 1e-9)
    print(f"F1 (P@1/R@3) : {f1:.0%}")
    print("\n--- 守卫（置信+词法）---")
    print(f"Chunk P@1 过守卫 : {stat['chunk1_guard']}/{n} = {stat['chunk1_guard']/n:.0%}  "
          f"(守卫误拒 {stat['false_reject']} 条正确命中)")
    fp_raw = sum(1 for g in neg if semantic.search(g["query"], top_k=3))
    fp_guard = sum(1 for g in neg
                   if semantic.search(g["query"], top_k=1) and
                   semantic.accept(g["query"], *semantic.search(g["query"], top_k=1)[0]))
    print(f"负样本原始假阳性 : {fp_raw}/{len(neg)}")
    print(f"负样本守卫后假阳性 : {fp_guard}/{len(neg)}  <- 目标 0")
    for note in ["fully_out", "partial_overlap"]:
        sub = [g for g in neg if g["note"] == note]
        if not sub:
            continue
        fp = sum(1 for g in sub
                 if semantic.search(g["query"], top_k=1) and
                 semantic.accept(g["query"], *semantic.search(g["query"], top_k=1)[0]))
        print(f"    {note:15s}: 守卫后假阳性 {fp}/{len(sub)}")
    for lvl in ["easy", "medium", "hard"]:
        sub = [g for g in pos if g["difficulty"] == lvl]
        ok = sum(1 for g in sub if any(hit_chunk(g, c) for c, _ in semantic.search(g["query"], 3)))
        print(f"  {lvl:6s}: {ok}/{len(sub)} = {ok/len(sub):.0%} chunk@3")
    if stat["cross_relevant"]:
        print(f"跨文档条文找回率 : {stat['cross_found']}/{stat['cross_relevant']} = "
              f"{stat['cross_found']/stat['cross_relevant']:.0%}")
    print("\n--- BM25 关键词基线（同语料同切分）---")
    print(f"BM25 chunk P@1 : {stat['bm25_1']}/{n} = {stat['bm25_1']/n:.0%}")
    print(f"BM25 chunk P@3 : {stat['bm25_3']}/{n} = {stat['bm25_3']/n:.0%}")
    print(f"\n样本: 正 {n} / 负 {len(neg)}（fully_out {sum(1 for g in neg if g['note']=='fully_out')} "
          f"+ partial_overlap {sum(1 for g in neg if g['note']=='partial_overlap')}）")


if __name__ == "__main__":
    main()
