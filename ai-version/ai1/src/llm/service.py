import asyncio
import json
import os
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from openai import AsyncOpenAI, APIStatusError, APITimeoutError, RateLimitError
from pydantic import ValidationError

from src.llm.schema import EnrichmentResponse

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PROMPT_PATH = os.path.join(PROJECT_ROOT, "prompts", "enrich-v1.md")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
PROMPT_VERSION = "enrich-v1"

MAX_ATTEMPTS = 3
BACKOFFS = [1.0, 2.0, 4.0]
JITTER_MAX = 0.5

os.makedirs(LOGS_DIR, exist_ok=True)


class LLMProviderError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


def load_system_prompt() -> str:
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def get_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=os.getenv("LLM_BASE_URL") or None,
        api_key=os.getenv("LLM_API_KEY") or None,
        max_retries=0,
        timeout=30.0,
    )


def log_attempt(
    *,
    attempt: int,
    duration_ms: float,
    model: str,
    error_type: Optional[str] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
) -> None:
    line: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "llm_attempt",
        "attempt": attempt,
        "duration_ms": round(duration_ms, 2),
        "model": model,
        "prompt_version": PROMPT_VERSION,
    }
    if error_type is not None:
        line["error_type"] = error_type
    if prompt_tokens is not None:
        line["prompt_tokens"] = prompt_tokens
    if completion_tokens is not None:
        line["completion_tokens"] = completion_tokens
    print(json.dumps(line))


async def call_model(
    client: AsyncOpenAI, model: str, messages: List[Dict[str, str]]
) -> Tuple[str, int, int]:
    last_error: Optional[Exception] = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        start = time.monotonic()
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
            )
            duration_ms = (time.monotonic() - start) * 1000
            usage = response.usage
            pt = usage.prompt_tokens if usage else 0
            ct = usage.completion_tokens if usage else 0
            content = response.choices[0].message.content or ""
            log_attempt(
                attempt=attempt,
                duration_ms=duration_ms,
                model=model,
                prompt_tokens=pt,
                completion_tokens=ct,
            )
            return content, pt, ct

        except RateLimitError as exc:
            duration_ms = (time.monotonic() - start) * 1000
            error_type = "rate_limit"
            log_attempt(
                attempt=attempt,
                duration_ms=duration_ms,
                model=model,
                error_type=error_type,
            )
            last_error = exc
            if attempt < MAX_ATTEMPTS:
                sleep_for = _retry_delay(exc, attempt)
                await asyncio.sleep(sleep_for)
                continue
            raise LLMProviderError(
                status_code=504,
                message=(
                    f"LLM retries exhausted after {MAX_ATTEMPTS} attempts "
                    "(last error: rate_limit)"
                ),
            )

        except APITimeoutError as exc:
            duration_ms = (time.monotonic() - start) * 1000
            error_type = "timeout"
            log_attempt(
                attempt=attempt,
                duration_ms=duration_ms,
                model=model,
                error_type=error_type,
            )
            last_error = exc
            if attempt < MAX_ATTEMPTS:
                sleep_for = (
                    BACKOFFS[min(attempt - 1, len(BACKOFFS) - 1)]
                    + random.uniform(0, JITTER_MAX)
                )
                await asyncio.sleep(sleep_for)
                continue
            raise LLMProviderError(
                status_code=504,
                message=(
                    f"LLM retries exhausted after {MAX_ATTEMPTS} attempts "
                    "(last error: timeout)"
                ),
            )

        except APIStatusError as exc:
            duration_ms = (time.monotonic() - start) * 1000
            if exc.status_code >= 500:
                error_type = f"http_{exc.status_code}"
                log_attempt(
                    attempt=attempt,
                    duration_ms=duration_ms,
                    model=model,
                    error_type=error_type,
                )
                last_error = exc
                if attempt < MAX_ATTEMPTS:
                    sleep_for = (
                        BACKOFFS[min(attempt - 1, len(BACKOFFS) - 1)]
                        + random.uniform(0, JITTER_MAX)
                    )
                    await asyncio.sleep(sleep_for)
                    continue
                raise LLMProviderError(
                    status_code=504,
                    message=(
                        f"LLM retries exhausted after {MAX_ATTEMPTS} attempts "
                        f"(last error: {error_type})"
                    ),
                )
            else:
                error_type = f"http_{exc.status_code}"
                log_attempt(
                    attempt=attempt,
                    duration_ms=duration_ms,
                    model=model,
                    error_type=error_type,
                )
                raise LLMProviderError(
                    status_code=502,
                    message=f"Provider error: HTTP {exc.status_code}",
                )

        except Exception as exc:
            duration_ms = (time.monotonic() - start) * 1000
            error_type = type(exc).__name__
            log_attempt(
                attempt=attempt,
                duration_ms=duration_ms,
                model=model,
                error_type=error_type,
            )
            raise LLMProviderError(
                status_code=502,
                message=f"Provider error: {error_type}",
            )

    raise LLMProviderError(
        status_code=504,
        message=f"LLM retries exhausted after {MAX_ATTEMPTS} attempts",
    )


def _retry_delay(exc: RateLimitError, attempt: int) -> float:
    try:
        retry_after = exc.response.headers.get("Retry-After")  # type: ignore[attr-defined]
        if retry_after:
            return float(retry_after)
    except Exception:
        pass
    return (
        BACKOFFS[min(attempt - 1, len(BACKOFFS) - 1)]
        + random.uniform(0, JITTER_MAX)
    )


def extract_json_object(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("\n", 1)
        text = parts[1] if len(parts) > 1 else ""
        if text.endswith("```"):
            text = text.rsplit("\n", 1)[0]
    text = text.replace("```", "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in model output")
    return text[start : end + 1]


def quarantine(
    record: Dict[str, Any], raw_output: str, error: str, model: str
) -> None:
    os.makedirs(LOGS_DIR, exist_ok=True)
    path = os.path.join(LOGS_DIR, "quarantine.jsonl")
    entry: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt_version": PROMPT_VERSION,
        "model": model,
        "error": error,
        "input_record": record,
        "raw_output": raw_output[:2000],
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def stub_response(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "category": "other",
        "summary": "Stubbed enrichment.",
        "quality_flags": ["no_flags"],
        "confidence": 0.5,
    }


async def enrich_record(record: Dict[str, Any]) -> EnrichmentResponse:
    model = os.getenv("LLM_MODEL")
    if not model:
        raise LLMProviderError(status_code=502, message="LLM_MODEL is not configured")

    system_prompt = load_system_prompt()
    client = get_client()

    user_content = json.dumps(record, ensure_ascii=False)

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    raw_output, _pt, _ct = await call_model(client, model, messages)

    try:
        json_str = extract_json_object(raw_output)
        parsed = json.loads(json_str)
        result = EnrichmentResponse.model_validate(parsed)
        return result
    except (ValueError, json.JSONDecodeError, ValidationError) as exc:
        validation_error = str(exc)
        repair_messages = messages + [
            {"role": "assistant", "content": raw_output},
            {
                "role": "user",
                "content": (
                    "Your previous answer was rejected for this reason: "
                    + validation_error
                    + ". Return only corrected JSON matching the schema."
                ),
            },
        ]
        try:
            raw_output2, _pt2, _ct2 = await call_model(client, model, repair_messages)
            json_str2 = extract_json_object(raw_output2)
            parsed2 = json.loads(json_str2)
            result = EnrichmentResponse.model_validate(parsed2)
            return result
        except Exception as exc2:
            quarantine(record, raw_output, str(exc2), model)
            raise LLMProviderError(
                status_code=422,
                message="Model output could not be parsed or validated after repair",
            )
