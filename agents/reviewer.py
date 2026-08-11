"""Independent Reviewer agent — verify findings against the RAG corpus.

Runs after the Judge: every violation finding is looked up in the regulation
corpus by its code_ref. If the standard's text is present in the KB, the finding
is marked "verified" with an evidence snippet; otherwise "manual check required".

No LLM is used in the review loop — it is a fast deterministic keyword lookup
so it never slows the main review flow. Standards whose full text is NOT in the
free corpus (paid SS / GB 500xx) correctly fall back to manual, matching the
paid-index policy.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
KB = REPO / "data" / "rag_kb"

# (code_ref fragment, corpus search term) — free standards only
_REF_TERMS = [
    ("Fire Code", "Fire Code"),
    ("FC23", "Fire Code"),
    ("GB 55037", "GB 55037"),
    ("GB 55036", "GB 55036"),
    ("Accessibility", "Code on Accessibility"),
    ("Approved Document", "Approved Document"),
]

_txt_cache = None


def _kb_txts():
    """(filename, text) for every searchable KB document (.txt, lazily OCR'd PDFs)."""
    global _txt_cache
    if _txt_cache is not None:
        return _txt_cache
    _txt_cache = []
    for p in sorted(KB.rglob("*.txt")):
        try:
            _txt_cache.append((p.name, p.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            pass
    # Fire Code 2023 is a text-layer PDF; extract to .txt once so lookups are fast.
    fc_pdf = KB / "SG_Free" / "02_fire_safety" / "Fire_Code_2023.pdf"
    fc_txt = fc_pdf.with_suffix(".txt")
    if fc_pdf.exists() and not fc_txt.exists():
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(fc_pdf))
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
            fc_txt.write_text(text, encoding="utf-8")
            _txt_cache.append((fc_txt.name, text))
        except Exception:
            pass
    return _txt_cache


def _term_for(code_ref):
    cr = code_ref or ""
    for key, term in _REF_TERMS:
        if key in cr:
            return term
    return None


def _search(code_ref):
    term = _term_for(code_ref)
    if not term:
        return None
    for fname, text in _kb_txts():
        if term in text:
            i = text.find(term)
            snippet = text[max(0, i - 60): i + 140].replace("\n", " ").strip()
            return f"{fname}: …{snippet}…"
    return None


def review_issues(issues):
    """Attach review_status (verified|manual) + evidence to each finding in place."""
    for iss in issues:
        ev = _search(iss.get("code_ref", ""))
        if ev:
            iss["review_status"] = "verified"
            iss["review_evidence"] = ev
        else:
            iss["review_status"] = "manual"
    return issues
