"""Extract the main legislative text from a saved Singapore Statutes Online page.

SSO act pages carry the statute body inside <div id="legisContent">. This strips
the surrounding nav chrome and writes clean text next to each saved HTML file.
Usage: python scripts/rag_kb/sso_html_to_txt.py <page.html> [page.html ...]
"""

import sys
from html.parser import HTMLParser
from pathlib import Path

BLOCK_TAGS = {"p", "div", "section", "li", "h1", "h2", "h3", "h4", "h5", "h6",
              "ul", "ol", "dl", "table", "tr", "blockquote"}


class LegisExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.in_target = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if not self.in_target:
            if dict(attrs).get("id") == "legisContent":
                self.in_target = True
                self.depth = 1
            return
        self.depth += 1
        if tag in BLOCK_TAGS:
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append("\t")

    def handle_startendtag(self, tag, attrs):
        if self.in_target and tag == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if not self.in_target:
            return
        self.depth -= 1
        if self.depth <= 0:
            self.in_target = False
            return
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.in_target:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = [ln.strip() for ln in raw.splitlines()]
        out = []
        for ln in lines:
            if not ln and out and not out[-1]:
                continue
            out.append(ln)
        return "\n".join(out).strip()


def extract(html: Path) -> str:
    p = LegisExtractor()
    p.feed(html.read_text(encoding="utf-8", errors="ignore"))
    return p.text()


def main() -> int:
    for arg in sys.argv[1:]:
        src = Path(arg)
        text = extract(src)
        dst = src.with_suffix(".txt")
        if not text:
            print(f"WARN: no legisContent found in {src} — skipped")
            continue
        dst.write_text(text, encoding="utf-8")
        print(f"{dst} ({len(text)} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
