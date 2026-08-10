"""Generate the RAG knowledge-base directory structure from kb_manifest.json.

Creates the folder tree under data/rag_kb, copies the manifest, and writes a
per-category _index.json metadata stub so each folder is self-describing for
the downstream ingestion step. Run: python scripts/rag_kb/create_kb_structure.py
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "scripts" / "rag_kb" / "kb_manifest.json"


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    kb_root = REPO_ROOT / manifest["kb_root"]
    kb_root.mkdir(parents=True, exist_ok=True)

    (kb_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    n_docs = 0
    for cat_key, cat in manifest["categories"].items():
        for sub_key, sub in cat["subdirs"].items():
            folder = kb_root / cat_key / sub_key
            folder.mkdir(parents=True, exist_ok=True)
            index = {
                "category": cat["label"],
                "subcategory": sub["label"],
                "documents": sub["documents"],
            }
            (folder / "_index.json").write_text(
                json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            n_docs += len(sub["documents"])

    print(f"KB structure created under {kb_root} — {n_docs} documents indexed.")


if __name__ == "__main__":
    main()
