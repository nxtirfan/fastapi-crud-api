"""Enrichment service: the one module that talks to the model (W7 · A17).

Stage 2: the prompt lives in prompts/enrich-v1.md (versioned file), the user's
record travels as a separate user message, JSON-encoded so it cannot break
out of its quotes, and the model answers at temperature 0.2.
"""

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

PROMPT_NAME = "enrich-v1.md"
PROMPT_VERSION = "v1"


def prompt_path() -> str:
    """Absolute path of the current, versioned prompt file."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "prompts", PROMPT_NAME)


def load_prompt() -> str:
    """Read the versioned prompt file from prompts/ (never a string in a route)."""
    with open(prompt_path(), encoding="utf-8") as file:
        return file.read()


def _client() -> OpenAI:
    return OpenAI(
        base_url=os.environ["LLM_BASE_URL"],
        api_key=os.environ["LLM_API_KEY"],
    )


def call_model(record: dict, extra: str | None = None) -> str:
    """Send the prompt (system) + the record (user, JSON-encoded) to the model.

    extra appends the repair instruction on the second attempt (Stage 3).
    """
    messages = [
        {"role": "system", "content": load_prompt()},
        {"role": "user", "content": json.dumps(record, ensure_ascii=False)},
    ]
    if extra:
        messages.append({"role": "user", "content": extra})
    res = _client().chat.completions.create(
        model=os.environ["LLM_MODEL"],
        messages=messages,
        temperature=0.2,
    )
    return res.choices[0].message.content


def stub_enrichment() -> dict:
    """Hard-coded answer that satisfies the schema, for LLM_STUB=1 mode.

    This is how every stage from here on is developed: server restarts and
    endpoint tests run against this, and a real model call happens only
    when a real answer is actually wanted.
    """
    return {
        "category": "other",
        "summary": "Stub mode: no model was called.",
        "quality_flags": ["no_flags"],
        "confidence": 0.0,
    }
