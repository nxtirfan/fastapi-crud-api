"""Enrichment service: the one module that talks to the model (W7 · A17).

Stage 2: the prompt lives in prompts/enrich-v1.md (versioned file), the user's
record travels as a separate user message, JSON-encoded so it cannot break
out of its quotes, and the model answers at temperature 0.2.

Stage 3: the model's answer is untrusted input, exactly like scraped HTML was
last week. parse_json strips code fences and finds the object, the Enrichment
schema validates it, a failed answer is repaired exactly once with its own
validation error, and an answer that is still broken goes to
logs/quarantine.jsonl — never to the caller, and the process never crashes.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import ValidationError

from src.llm.schema import Enrichment

load_dotenv()

PROMPT_NAME = "enrich-v1.md"
PROMPT_VERSION = "v1"
ROOT = Path(__file__).resolve().parents[2]
QUARANTINE_LOG = ROOT / "logs" / "quarantine.jsonl"


class QuarantinedError(Exception):
    """The model's answer failed validation twice; its raw output is in the log."""


def prompt_path() -> str:
    """Absolute path of the current, versioned prompt file."""
    return str(ROOT / "prompts" / PROMPT_NAME)


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


def parse_json(text: str) -> dict:
    """Extract a JSON object from model text: strip the code fence, find the braces."""
    if not text or not text.strip():
        raise ValueError("empty response from model")
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()[1:]  # drop the opening fence (``` or ```json)
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    start, end = stripped.find("{"), stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object found in model text")
    return json.loads(stripped[start:end + 1])


def _parse_and_validate(raw: str) -> tuple[Enrichment | None, str | None]:
    """Parse + validate one model answer. Returns (enrichment, None) or (None, error)."""
    try:
        data = parse_json(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        return None, f"not parseable JSON: {exc}"
    try:
        return Enrichment.model_validate(data), None
    except ValidationError as exc:
        return None, f"schema validation failed: {exc}"


def _quarantine(record: dict, error: str, raw: str) -> None:
    """Append the twice-failed answer to logs/quarantine.jsonl. Then give up."""
    QUARANTINE_LOG.parent.mkdir(exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "prompt_version": PROMPT_VERSION,
        "model": os.environ.get("LLM_MODEL", "?"),
        "error": error,
        "input": record,
        "raw_output": (raw or "")[:2000],
    }
    with open(QUARANTINE_LOG, "a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")


def enrich(record: dict) -> Enrichment:
    """Call the model, parse, validate. Repair exactly once. Then quarantine."""
    enrichment, error = _parse_and_validate(call_model(record))
    if enrichment is not None:
        return enrichment
    repair = (
        "Your previous answer was rejected for this reason: " + error
        + " Return only corrected JSON matching the schema — no code fences, no commentary."
    )
    raw2 = call_model(record, extra=repair)
    enrichment, second_error = _parse_and_validate(raw2)
    if enrichment is not None:
        return enrichment
    _quarantine(record, second_error, raw2)
    raise QuarantinedError(second_error)


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
