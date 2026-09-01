"""Enrichment service: the one module that talks to the model (W7 · A17).

Stage 1 contains no model call yet - it only builds the prompt file path
and the stub answer, so the endpoint can be built and tested at zero cost.
"""

import os

PROMPT_NAME = "enrich-v1.md"


def prompt_path() -> str:
    """Absolute path of the current, versioned prompt file."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "prompts", PROMPT_NAME)


def load_prompt() -> str:
    """Read the versioned prompt file from prompts/ (never a string in a route)."""
    with open(prompt_path(), encoding="utf-8") as file:
        return file.read()


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
