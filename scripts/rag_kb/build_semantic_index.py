"""Build the semantic index over the free RAG corpus.

Usage:  python scripts/rag_kb/build_semantic_index.py
Writes: data/rag_kb/_semantic/{index.npz, chunks.json}

The corpus is the free .txt KB documents (Fire Code 2023, GB 55037, BCA/FSA
regs...); paid indexes and metadata are excluded. Requires the multilingual
embedding model to be cached (downloaded via proxy, see kb/semantic.MODEL_NAME).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from kb.semantic import build_index

if __name__ == "__main__":
    sys.stdout = sys.stdout if sys.stdout.encoding.lower().startswith("utf") \
        else __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    n = build_index()
    print(f"indexed {n} chunks" if n else "no free corpus found")
