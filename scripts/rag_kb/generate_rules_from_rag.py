"""Generate JSON rules from RAG regulation text via the LLM, for human review.

KB Steward agent's rule-authoring loop: read a regulation clause from the RAG
corpus (data/rag_kb), ask the LLM to draft JSON rules, validate their schema,
and save them for human confirmation. Rules are NOT written into
data/standards automatically — they land there only after a human confirms.

Usage: python scripts/rag_kb/generate_rules_from_rag.py <rag_text.txt>
       [--std cn|sg] [--category civil|eee|building] [--clause 关键词]
       [--out output/proposed_rules.json]
"""

import argparse
import json
import sys
from pathlib import Path

from llm import client

REPO = Path(__file__).resolve().parents[2]
OPERATORS = {"<=", ">=", ">", "<", "==", "!=", "in", "not_in"}
REQUIRED = {"id", "name", "field", "operator", "threshold", "severity",
            "code_ref", "message"}


def extract_chunk(text, keyword=None, max_chars=2000):
    """Locate a clause by keyword and return a bounded chunk around it."""
    if keyword:
        i = text.find(keyword)
        if i >= 0:
            return text[max(0, i - 200): i + max_chars]
    return text[:max_chars]


def validate_rules(rules):
    """Return (valid, invalid) rule lists after schema checks."""
    valid, invalid = [], []
    for r in rules:
        if not isinstance(r, dict):
            invalid.append(("not a dict", r))
            continue
        missing = REQUIRED - set(r)
        if missing:
            invalid.append((f"missing {sorted(missing)}", r))
            continue
        if r.get("operator") not in OPERATORS:
            invalid.append((f"bad operator {r.get('operator')}", r))
            continue
        valid.append(r)
    return valid, invalid


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("text", help="regulation text file (e.g. data/rag_kb/...txt)")
    ap.add_argument("--std", default="cn", choices=["cn", "sg"])
    ap.add_argument("--category", default="civil", choices=["civil", "eee", "building"])
    ap.add_argument("--clause", help="keyword locating the clause chunk")
    ap.add_argument("--out", default=None, help="output json (default output/proposed_rules.json)")
    args = ap.parse_args()

    text = Path(args.text).read_text(encoding="utf-8")
    chunk = extract_chunk(text, args.clause)
    print(f"[LLM] drafting {args.category} rules for {args.std} "
          f"(clause chunk {len(chunk)} chars)...")
    if not client.available():
        sys.exit("anthropic SDK not available — cannot call the LLM.")
    rules = client.generate_rules_from_code(chunk, std_id=args.std, category=args.category)
    if not rules:
        sys.exit("LLM returned no parseable rules (upstream unreachable or malformed).")

    valid, invalid = validate_rules(rules)
    print(f"\n== {len(valid)} valid, {len(invalid)} invalid ==")
    for r in valid:
        print(f"  [{r['severity']}] {r['id']} {r['name']} | "
              f"{r['field']} {r['operator']} {r['threshold']} | {r['code_ref']}")
    for reason, r in invalid[:5]:
        print(f"  [INVALID {reason}] {json.dumps(r, ensure_ascii=False)[:160]}")

    out = Path(args.out) if args.out else REPO / "output" / "proposed_rules.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "std": args.std, "category": args.category,
        "source": str(Path(args.text).name),
        "rules": valid, "invalid": invalid,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {len(valid)} proposed rules to {out}. Review, then copy confirmed "
          f"rules into data/standards/{args.std}/<category>_rules.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
