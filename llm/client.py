"""DeepSeek (OpenAI-compatible) client.

DeepSeek is used for the *reasoning / generation* layer, never for numeric
compliance judgment (that stays in core/engine.py's deterministic rule engine):
  1. review narrative  — rule-engine findings -> natural-language report + fixes
  2. rule authoring    — code clauses -> JSON rules
  3. coordinator       — LLM explains cross-discipline conflicts + resolution order
"""
import os

from openai import OpenAI

BASE_URL = "https://api.deepseek.com"
CHAT_MODEL = "deepseek-chat"
REASON_MODEL = "deepseek-reasoner"


def get_client():
    """Build a DeepSeek client from the DEEPSEEK_API_KEY environment variable."""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set.")
    return OpenAI(api_key=api_key, base_url=BASE_URL)


def chat(messages, model=CHAT_MODEL, temperature=0.3, max_tokens=2000):
    """Simple chat completion wrapper. Returns the assistant text."""
    client = get_client()
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""


def generate_review_narrative(issues, standard_meta):
    """Turn structured review findings into a professional review report."""
    raise NotImplementedError("Review narrative generation is not implemented yet.")


def coordinate_conflicts(conflicts, standard_meta):
    """Explain conflict zones and propose a coordinated resolution order."""
    raise NotImplementedError("LLM conflict coordination is not implemented yet.")
