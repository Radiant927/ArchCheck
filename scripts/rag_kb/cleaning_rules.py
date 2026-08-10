"""Detect superseded / wrong code references in rule JSON files or a text corpus.

Rules:
    python scripts/rag_kb/cleaning_rules.py --rules
        # scan data/standards/**/*.json (the project's own rule code_refs)
    python scripts/rag_kb/cleaning_rules.py --corpus <dir>
        # scan collected KB documents (.txt/.md/.json) for stale citations

Exit code is 1 if any ERROR-level issue is found, else 0.
"""

import argparse
import json
import re
import sys
from pathlib import Path

# KB metadata files describe supersession warnings rather than committing them;
# they are not document corpus, so skip them when scanning a corpus directory.
METADATA_FILES = {"manifest.json", "_index.json"}

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RULES_GLOB = "data/standards/*/*.json"

# (main_pattern, required_context_or_None, ignore_pattern_or_None, severity, message)
# A hit fires only when main matches AND context appears within WINDOW chars of
# the match AND no ignore token does. Windowed matching keeps whole-document
# scans precise: "Formerly CP 5" tables, a distant "emergency lighting" mention,
# or "CP 52" (a different legacy code) no longer trigger false hits.
WINDOW = 80

CHECKS = [
    (re.compile(r"CP\s*5\b", re.I), None, re.compile(r"former(ly)?\s*CP\s*5\b", re.I),
     "error", "CP 5 已被 SS 638:2018（电气装置规范）取代"),
    (re.compile(r"GB\s*50045", re.I), None, None,
     "error", "GB 50045 已由 GB 50016-2014 取代，禁止引用"),
    (re.compile(r"GB\s*55037\s*[-—]?\s*2025", re.I), None, None,
     "error", "版本错误：应为 GB 55037-2022"),
    (re.compile(r"SS\s*551", re.I), re.compile(r"应急照明|emergency\s*light|emergency\s*power|evacuation", re.I), None,
     "error", "SS 551 是接地规范；应急照明应为 SS 563"),
    (re.compile(r"SS\s*575", re.I), re.compile(r"应急照明|emergency\s*light", re.I), None,
     "error", "SS 575 是消防栓/消防卷盘规范；应急照明应为 SS 563"),
    (re.compile(r"GB\s*50016", re.I), re.compile(r"5\.3\.1|5\.5\.1[78]|防火分区|疏散|fire\s*compartment", re.I), None,
     "info", "强制值请对照 GB 55037-2022（GB 50016 强条已被通用规范取代，保留作设计参考）"),
    (re.compile(r"GB\s*(51309|50974|50116|50084)", re.I), None, None, "info",
     "本规范强制条文已由 GB 55036-2022 取代，仅作细节参考"),
]


def _scan_text(text: str) -> list[tuple[str, str]]:
    hits = []
    for main, ctx, ignore, sev, msg in CHECKS:
        for m in main.finditer(text):
            lo = max(0, m.start() - WINDOW)
            hi = min(len(text), m.end() + WINDOW)
            window = text[lo:hi]
            if ignore and ignore.search(window):
                continue
            if ctx and not ctx.search(window):
                continue
            hits.append((sev, msg))
    return hits


def _scan_rules_json(path: Path) -> list[tuple[str, str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []
    rules = data if isinstance(data, list) else data.get("rules", [])
    hits = []
    for r in rules:
        if not isinstance(r, dict):
            continue
        blob = " ".join(str(r.get(k, "")) for k in ("id", "name", "code_ref", "message"))
        rid = r.get("id", path.name)
        hits += [(sev, f"{rid}: {msg}") for sev, msg in _scan_text(blob)]
    return hits


def _pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        from PyPDF2 import PdfReader
    try:
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def _scan_corpus(directory: Path) -> list[tuple[str, str]]:
    hits = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.name in METADATA_FILES:
            continue
        suffix = path.suffix.lower()
        if suffix in {".txt", ".md", ".json"}:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
        elif suffix == ".pdf":
            text = _pdf_text(path)
            if not text:
                continue  # scanned/image-only PDF has no text layer to check
        else:
            continue
        rel = path.relative_to(directory)
        hits += [(sev, f"{rel}: {msg}") for sev, msg in _scan_text(text)]
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--rules", action="store_true", help="scan project rule JSON code_refs")
    grp.add_argument("--corpus", metavar="DIR", help="scan a collected text corpus directory")
    args = ap.parse_args()

    if args.rules:
        paths = sorted(REPO_ROOT.glob(DEFAULT_RULES_GLOB))
        hits = [h for p in paths for h in _scan_rules_json(p)]
    else:
        hits = _scan_corpus(Path(args.corpus))

    errors = [h for h in hits if h[0] == "error"]
    infos = [h for h in hits if h[0] == "info"]
    for sev, msg in hits:
        print(f"[{sev.upper()}] {msg}")

    print(f"\n{len(hits)} hit(s): {len(errors)} error, {len(infos)} info.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
