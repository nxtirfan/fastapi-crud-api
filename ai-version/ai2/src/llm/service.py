import os
import json
import time
import random
import logging
from pathlib import Path
from typing import Optional, Tuple
from openai import OpenAI
from openai import APITimeoutError, APIConnectionError, RateLimitError, APIStatusError
from src.llm.schema import EnrichResponse, CategoryEnum, QualityFlagEnum

PROMPT_VERSION = "enrich-v1"
PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / f"{PROMPT_VERSION}.md"

LOGS_DIR = Path(__file__).parent.parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
QUARANTINE_PATH = LOGS_DIR / "quarantine.jsonl"

STUB_RESPONSE = EnrichResponse(
    category=CategoryEnum.other,
    summary="Stub response for testing.",
    quality_flags=[QualityFlagEnum.no_flags],
    confidence=0.5
)


def load_system_prompt() -> str:
    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def build_user_message(title: str, description: str, price_gbp: float) -> str:
    record = {
        "title": title,
        "description": description,
        "price_gbp": price_gbp
    }
    return json.dumps(record, ensure_ascii=False)


def log_cost(
    event: str,
    attempt: int,
    duration_ms: int,
    model: str,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    error_type: Optional[str] = None
):
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event": event,
        "attempt": attempt,
        "duration_ms": duration_ms,
        "model": model,
        "prompt_version": PROMPT_VERSION,
    }
    if prompt_tokens is not None:
        log_entry["prompt_tokens"] = prompt_tokens
    if completion_tokens is not None:
        log_entry["completion_tokens"] = completion_tokens
    if error_type is not None:
        log_entry["error_type"] = error_type
    print(json.dumps(log_entry), flush=True)


def log_quarantine(
    model: str,
    error: str,
    input_record: dict,
    raw_output: str
):
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "prompt_version": PROMPT_VERSION,
        "model": model,
        "error": error,
        "input_record": input_record,
        "raw_output": raw_output[:2000]
    }
    with open(QUARANTINE_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def parse_model_output(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        raw = raw[start:end+1]
    return json.loads(raw)


def validate_response(data: dict) -> EnrichResponse:
    return EnrichResponse(**data)


def get_client() -> OpenAI:
    base_url = os.getenv("LLM_BASE_URL")
    api_key = os.getenv("LLM_API_KEY")
    return OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=30.0,
        max_retries=0
    )


async def call_model(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_message: str,
    attempt: int
) -> Tuple[dict, int, int]:
    start = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.2,
            response_format={"type": "json_object"}
        )
        duration_ms = int((time.perf_counter() - start) * 1000)
        raw_content = response.choices[0].message.content
        prompt_tokens = response.usage.prompt_tokens if response.usage else 0
        completion_tokens = response.usage.completion_tokens if response.usage else 0
        log_cost("model_call_success", attempt, duration_ms, model, prompt_tokens, completion_tokens)
        return parse_model_output(raw_content), prompt_tokens, completion_tokens
    except (APITimeoutError, APIConnectionError) as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_cost("model_call_retryable_error", attempt, duration_ms, model, error_type=type(e).__name__)
        raise
    except RateLimitError as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_cost("model_call_retryable_error", attempt, duration_ms, model, error_type="RateLimitError")
        raise
    except APIStatusError as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        if e.status_code >= 500:
            log_cost("model_call_retryable_error", attempt, duration_ms, model, error_type=f"HTTP_{e.status_code}")
            raise
        else:
            log_cost("model_call_fatal_error", attempt, duration_ms, model, error_type=f"HTTP_{e.status_code}")
            raise HTTPException(status_code=502, detail=f"Upstream error: HTTP {e.status_code}")
    except Exception as e:
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_cost("model_call_fatal_error", attempt, duration_ms, model, error_type=type(e).__name__)
        raise HTTPException(status_code=502, detail=f"Upstream error: {str(e)}")


async def enrich_book(title: str, description: str, price_gbp: float) -> EnrichResponse:
    if os.getenv("LLM_STUB", "0") == "1":
        log_cost("stub_response", 1, 0, "stub")
        return STUB_RESPONSE

    model = os.getenv("LLM_MODEL")
    if not model:
        raise HTTPException(status_code=500, detail="LLM_MODEL not configured")

    client = get_client()
    system_prompt = load_system_prompt()
    user_message = build_user_message(title, description, price_gbp)

    max_attempts = 3
    base_delays = [1.0, 2.0, 4.0]

    last_error = None
    last_raw_output = None

    for attempt in range(1, max_attempts + 1):
        try:
            parsed, prompt_tokens, completion_tokens = await call_model(
                client, model, system_prompt, user_message, attempt
            )
            validated = validate_response(parsed)
            return validated
        except HTTPException:
            raise
        except (APITimeoutError, APIConnectionError, RateLimitError) as e:
            last_error = e
            if attempt < max_attempts:
                delay = base_delays[attempt - 1] + random.uniform(0, 0.5)
                if isinstance(e, RateLimitError) and hasattr(e, 'response') and e.response is not None:
                    retry_after = e.response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            delay = max(delay, float(retry_after))
                        except ValueError:
                            pass
                time.sleep(delay)
                continue
            else:
                log_cost("retries_exhausted", attempt, 0, model, error_type=type(e).__name__)
                raise HTTPException(status_code=504, detail="Upstream timeout after retries")
        except Exception as e:
            last_error = e
            last_raw_output = getattr(e, 'raw_output', None)
            break

    if last_raw_output is None and hasattr(last_error, 'raw_output'):
        last_raw_output = last_error.raw_output

    repair_prompt = system_prompt + "\n\nYour previous answer was rejected for this reason: " + str(last_error) + "\nReturn only corrected JSON matching the schema."
    try:
        parsed, prompt_tokens, completion_tokens = await call_model(
            client, model, repair_prompt, user_message, max_attempts + 1
        )
        validated = validate_response(parsed)
        return validated
    except Exception as repair_error:
        error_msg = f"Repair failed: {str(repair_error)}"
        log_quarantine(model, error_msg, {"title": title, "description": description, "price_gbp": price_gbp}, last_raw_output or "")
        raise HTTPException(status_code=422, detail="Model output could not be validated after repair")


from fastapi import HTTPException
from datetime import datetime
