"""Semantic retrieval over the free RAG corpus (bge-m3 multilingual embeddings).

Builds / loads a chunked, vectorised index of the free .txt KB documents and
answers evidence queries with cosine similarity. Degrades gracefully to empty
results when the model or index is unavailable (caller falls back to keyword).

Model: BAAI/bge-m3 (multilingual zh+en, 8192 ctx), CLS-pooled + L2-normalised.
Downloads from ModelScope when the HF cache is empty (network-friendly).
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
KB = REPO / "data" / "rag_kb"
INDEX_DIR = KB / "_semantic"
MODEL_NAME = "BAAI/bge-m3"

CHUNK_SIZE = 800      # chars per chunk (bge-m3 has 8K ctx; larger = better context)
CHUNK_OVERLAP = 160
MAX_TOKENS = 512

# directories that are paid / metadata only — never indexed
_SKIP_DIRS = {"SG_Paid_Index", "CN_Reference"}

# corpus-noise patterns from the OCR / PDF-text extraction stage
_PAGE_MARK = re.compile(r"^=+\s*第\s*\d+\s*页\s*/\s*page\s*\d+\s*=+$", re.IGNORECASE)
_REV_LINE = re.compile(r"^dated\s+\d{1,2}\s+[A-Z][a-z]{2}(?:\s+\d{4})?", re.IGNORECASE)
_REV_INLINE = re.compile(r"\(\s*dated\s+\d{1,2}\s+[A-Z][a-z]{2}\s+\d{4}\s*\)")


def _clean_text(text):
    """Strip OCR page markers and Fire Code revision annotations (line + inline)."""
    out = []
    for ln in text.splitlines():
        s = ln.strip()
        if _PAGE_MARK.match(s) or (_REV_LINE.match(s) and len(s) < 40):
            continue
        out.append(_REV_INLINE.sub("", ln))
    return "\n".join(out)

_tokenizer = None
_model = None
_chunks = None
_vectors = None
_model_path = None
_onnx_sess = None


def _model_local_path():
    """Path to a cached bge-m3: HF cache first, else ModelScope snapshot dir."""
    global _model_path
    if _model_path is not None:
        return _model_path
    from huggingface_hub import try_to_load_from_cache
    if try_to_load_from_cache(MODEL_NAME, "config.json"):
        _model_path = MODEL_NAME
    else:
        ms_snapshot = (Path.home() / ".cache" / "modelscope" / "models"
                       / "BAAI--bge-m3" / "snapshots" / "master")
        if (ms_snapshot / "config.json").exists():
            _model_path = str(ms_snapshot)
        else:
            try:
                from modelscope import snapshot_download
                _model_path = snapshot_download(MODEL_NAME)
            except Exception:
                _model_path = MODEL_NAME
    return _model_path


def _free_txts():
    """Yield (path) for every searchable free KB .txt (paid index excluded)."""
    for p in sorted(KB.rglob("*.txt")):
        rel = p.relative_to(KB)
        if rel.parts and rel.parts[0] in _SKIP_DIRS:
            continue
        if p.name in ("manifest.json", "_index.json"):
            continue
        yield p


def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Split a document into overlapping passages (paragraph-aware)."""
    paras = re.split(r"\n\s*\n", text)
    chunks = []
    cur = ""
    for p in paras:
        p = p.strip()
        if not p:
            continue
        if not cur:
            cur = p
        elif len(cur) + len(p) + 1 <= size:
            cur += "\n" + p
        else:
            chunks.append(cur)
            if len(p) > size:
                for i in range(0, len(p), size - overlap):
                    chunks.append(p[i:i + size])
                cur = ""
            else:
                cur = p
    if cur:
        chunks.append(cur)
    return chunks


def _load_model():
    global _tokenizer, _model
    if _model is not None:
        return
    from transformers import AutoModel, AutoTokenizer
    path = _model_local_path()
    _tokenizer = AutoTokenizer.from_pretrained(path)
    _model = AutoModel.from_pretrained(path)
    _model.eval()


def embed(texts):
    """L2-normalised CLS embeddings (numpy). ONNX Runtime first (much faster on
    CPU), then PyTorch fallback."""
    try:
        if _load_onnx():
            return _embed_onnx(texts)
    except Exception:
        pass
    _load_model()
    import torch
    import torch.nn.functional as F
    inputs = _tokenizer(texts, padding=True, truncation=True,
                        max_length=MAX_TOKENS, return_tensors="pt")
    with torch.no_grad():
        out = _model(**inputs)
    pooled = out.last_hidden_state[:, 0]      # bge uses the CLS token
    return F.normalize(pooled, p=2, dim=1).numpy()


def _load_onnx():
    """Lazy ONNX Runtime session over the bundled bge-m3 onnx export (fast CPU)."""
    global _onnx_sess, _tokenizer
    if _onnx_sess is not None:
        return True
    import onnxruntime as ort
    onnx_path = Path(_model_local_path()) / "onnx" / "model.onnx"
    if not onnx_path.exists():
        return False
    from transformers import AutoTokenizer
    _tokenizer = AutoTokenizer.from_pretrained(_model_local_path())
    _onnx_sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    return True


def _embed_onnx(texts):
    import numpy as np
    inputs = _tokenizer(texts, padding=True, truncation=True,
                        max_length=MAX_TOKENS, return_tensors="np")
    outs = _onnx_sess.run(None, {
        "input_ids": inputs["input_ids"].astype(np.int64),
        "attention_mask": inputs["attention_mask"].astype(np.int64)})
    pooled = np.asarray(outs[0])[:, 0]        # CLS token
    norms = np.linalg.norm(pooled, axis=1, keepdims=True)
    return pooled / norms


def build_index():
    """Chunk every free KB txt and write index.npz + chunks.json. Returns count."""
    doc_chunks = []
    for p in _free_txts():
        try:
            text = _clean_text(p.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        for c in chunk_text(text):
            doc_chunks.append((p.name, c))
    if not doc_chunks:
        return None
    bs = 32
    vecs = []
    total = len(doc_chunks)
    for i in range(0, total, bs):
        batch = [c for _, c in doc_chunks[i:i + bs]]
        vecs.append(embed(batch))
        done = min(i + bs, total)
        print(f"  embedded {done}/{total} chunks ({done / total:.0%})", flush=True)
    vecs = np.vstack(vecs)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    np.savez(INDEX_DIR / "index.npz", vectors=vecs.astype("float32"))
    with open(INDEX_DIR / "chunks.json", "w", encoding="utf-8") as f:
        json.dump([{"doc": d, "text": t} for d, t in doc_chunks], f, ensure_ascii=False)
    return len(doc_chunks)


def _load_index():
    global _chunks, _vectors
    if _chunks is not None:
        return True
    np_path = INDEX_DIR / "index.npz"
    json_path = INDEX_DIR / "chunks.json"
    if not (np_path.exists() and json_path.exists()):
        return False
    with open(json_path, "r", encoding="utf-8") as f:
        _chunks = json.load(f)
    _vectors = np.load(np_path)["vectors"]
    return True


# generic words that shouldn't count as lexical confirmation (incl. building/plan terms)
_EN_STOP = set("""
a an the of for in on to with shall be is are was were not more than and or as at by from
this that these those it its no nor but do does did have has had
area building buildings floor floors roof shall provided except following
""".split())


def _tokens(s):
    """Content tokens of a text: non-stopword ASCII words + CJK bigrams."""
    toks = set(w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in _EN_STOP)
    cjk = re.findall(r"[一-鿿]", s)
    toks |= {"".join(b) for b in zip(cjk, cjk[1:])}
    return toks


# corpus-generic terms that appear in nearly every chunk — a lexical overlap made
# only of these is not evidence the chunk answers the query.
_GENERIC_TOKENS = {
    "要求", "建筑", "消防", "防火", "设计", "设置", "规定", "场地", "楼层",
    "位置", "什么", "多少", "以及", "进行", "下列", "本条", "符合", "采用",
    "shall", "building", "buildings", "fire", "and", "or", "the", "of", "for",
    "provided", "except", "area", "floor", "required", "install", "design",
}


def _lexical_confirm(query, chunk):
    return bool((_tokens(query) - _GENERIC_TOKENS) & (_tokens(chunk["text"]) - _GENERIC_TOKENS))


def accept(query, chunk, score):
    """Confidence guard: semantic hit must also have lexical confirmation.

    bge-m3 cosine scores cluster in ~0.5-0.8, so a raw score threshold cannot
    separate relevant from out-of-corpus noise. We additionally require the top
    chunk to share a *non-generic* content token/bigram with the query (unless
    the score is very high). The generic-term filter stops a single shared word
    like "要求" or "建筑" from passing. This lowers the out-of-corpus
    false-positive rate; it cannot eliminate it (a small single-domain corpus
    has irreducible domain overlap), so the reviewer still falls back to keyword
    → manual.
    """
    if score < 0.60:
        return False
    if score >= 0.82:
        return True
    return _lexical_confirm(query, chunk)


def search(query, top_k=5):
    """Top-k [(chunk, score)] for a query; [] if index/model unavailable."""
    if not _load_index():
        return []
    try:
        qv = embed([query])
    except Exception:
        return []
    scores = _vectors @ qv.T[:, 0]
    order = np.argsort(-scores)[:top_k]
    return [(_chunks[i], float(scores[i])) for i in order]


if __name__ == "__main__":
    sys.stdout = sys.stdout if sys.stdout.encoding.lower().startswith("utf") \
        else __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    q = sys.argv[1] if len(sys.argv) > 1 else "走廊疏散距离 消防"
    if not _load_index():
        print("index not built yet — run scripts/rag_kb/build_semantic_index.py")
        sys.exit(1)
    for chunk, score in search(q):
        print(f"[{score:.3f}] {chunk['doc']}: {chunk['text'][:90].replace(chr(10), ' ')}...")
