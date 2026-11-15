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
import random
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)
from pydantic import ValidationError

from src.llm.schema import Enrichment

load_dotenv()

PROMPT_NAME = "enrich-v1.md"
PROMPT_VERSION = "v1"
ROOT = Path(__file__).resolve().parents[2]
QUARANTINE_LOG = ROOT / "logs" / "quarantine.jsonl"

# Stage 4 policy, written down instead of left to SDK defaults:
CALL_TIMEOUT_SECONDS = 30.0          # SDK default is 600 s — that holds an HTTP connection open for ten minutes
MAX_ATTEMPTS = 3                     # 1 first try + up to 2 retries, decided here, not silently by the SDK


class QuarantinedError(Exception):
    """The model's answer failed validation twice; its raw output is in the log."""


class LLMCallError(Exception):
    """Base: the model call failed in a way the route must translate."""


class ModelAuthError(LLMCallError):
    """400/401/403 — never retried; a bad key is still a bad key in four seconds."""


class ModelUnavailableError(LLMCallError):
    """Timeout/429/5xx exhausted after MAX_ATTEMPTS — the provider is unreachable."""


class RateLimited(Exception):
    def __init__(self, cause, retry_after: float | None):
        self.cause = cause
        self.retry_after = retry_after


class Retriable(Exception):
    def __init__(self, cause):
        self.cause = cause


def prompt_path() -> str:
    """Absolute path of the current, versioned prompt file."""
    return str(ROOT / "prompts" / PROMPT_NAME)


def load_prompt() -> str:
    """Read the versioned prompt file from prompts/ (never a string in a route)."""
    with open(prompt_path(), encoding="utf-8") as file:
        return file.read()


def _client() -> OpenAI:
    # max_retries=0: the SDK's own two silent retries are OFF — this module owns
    # the retry policy (which errors, how many, how long) and logs every attempt.
    return OpenAI(
        base_url=os.environ["LLM_BASE_URL"],
        api_key=os.environ["LLM_API_KEY"],
        timeout=CALL_TIMEOUT_SECONDS,
        max_retries=0,
    )


def _backoff_seconds(attempt: int, retry_after: float | None) -> float:
    """1s, 2s, 4s, each plus up to 0.5s of jitter. Retry-After overrides on 429."""
    if retry_after is not None:
        return min(retry_after, 15.0)
    return min(2 ** (attempt - 1), 4) + random.uniform(0, 0.5)


def _cost_log(**fields) -> None:
    """One structured JSON line per attempt, to stdout (twelve-factor logs)."""
    line = json.dumps(
        {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **fields},
        ensure_ascii=False,
    )
    print(line, flush=True)


def _create(messages: list[dict], attempt: int):
    """One model attempt: measures itself, logs cost, classifies the failure."""
    start = time.perf_counter()
    try:
        res = _client().chat.completions.create(
            model=os.environ["LLM_MODEL"],
            messages=messages,
            temperature=0.2,
        )
    except Exception as exc:
        duration_ms = round((time.perf_counter() - start) * 1000)
        _cost_log(event="error", attempt=attempt, duration_ms=duration_ms, error=type(exc).__name__)
        if isinstance(exc, APITimeoutError):  # before APIConnectionError (its parent)
            raise Retriable(exc)
        if isinstance(exc, APIConnectionError):
            raise Retriable(exc)
        if isinstance(exc, RateLimitError):
            retry_after = None
            response = getattr(exc, "response", None)
            if response is not None:
                raw = response.headers.get("retry-after")
                if raw is not None:
                    try:
                        retry_after = float(raw)
                    except ValueError:
                        retry_after = None
            raise RateLimited(exc, retry_after)
        status = getattr(exc, "status_code", None)
        if status is not None and status >= 500:
            raise Retriable(exc)
        raise ModelAuthError(str(exc))  # 400/401/403 and anything else: never retried
    duration_ms = round((time.perf_counter() - start) * 1000)
    usage = res.usage
    _cost_log(
        event="call", attempt=attempt, duration_ms=duration_ms,
        model=os.environ["LLM_MODEL"], prompt_version=PROMPT_VERSION,
        prompt_tokens=usage.prompt_tokens, completion_tokens=usage.completion_tokens,
    )
    return res


def _call_with_policy(messages: list[dict]):
    """Run the retry policy: only timeout/429/5xx are retried, with backoff+jitter."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return _create(messages, attempt)
        except RateLimited as exc:
            if attempt == MAX_ATTEMPTS:
                raise ModelUnavailableError(str(exc.cause)) from exc.cause
            time.sleep(_backoff_seconds(attempt, exc.retry_after))
        except Retriable as exc:
            if attempt == MAX_ATTEMPTS:
                raise ModelUnavailableError(str(exc.cause)) from exc.cause
            time.sleep(_backoff_seconds(attempt, None))
    raise ModelUnavailableError("exhausted retries")


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
    res = _call_with_policy(messages)
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
