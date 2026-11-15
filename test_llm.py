"""Unit tests for the /enrich LLM plumbing (W7 · A17) — zero model calls.

service.call_model is monkeypatched everywhere: these tests prove the parse,
repair-once, quarantine and kill-switch behaviour without spending quota.
"""

import json

import pytest
from fastapi.testclient import TestClient

import main
from src.llm import service
from src.llm.schema import Enrichment

VALID = {
    "category": "poetry",
    "summary": "A short summary.",
    "quality_flags": ["no_flags"],
    "confidence": 0.9,
}


def _json(obj) -> str:
    return json.dumps(obj)


def _client() -> TestClient:
    return TestClient(main.app)


# --- parse_json -----------------------------------------------------------

def test_parse_json_plain():
    assert service.parse_json(_json(VALID)) == VALID


def test_parse_json_code_fenced():
    assert service.parse_json("```json\n" + _json(VALID) + "\n```") == VALID


def test_parse_json_with_prose():
    assert service.parse_json("Sure! Here is the JSON:\n" + _json(VALID) + " hope that helps") == VALID


def test_parse_json_empty_raises():
    with pytest.raises(ValueError):
        service.parse_json("")


def test_parse_json_no_braces_raises():
    with pytest.raises(ValueError):
        service.parse_json("no json here at all")


# --- enrich: repair-once and quarantine -----------------------------------

def test_enrich_happy_path(monkeypatch):
    calls = []
    monkeypatch.setattr(service, "call_model", lambda record, extra=None: calls.append(record) or _json(VALID))
    result = service.enrich({"title": "x"})
    assert result == Enrichment.model_validate(VALID)
    assert len(calls) == 1


def test_enrich_repairs_exactly_once(monkeypatch):
    calls = []

    def fake_call(record, extra=None):
        calls.append(extra)
        if len(calls) == 1:
            return _json({"category": "mystery", **{k: v for k, v in VALID.items() if k != "category"}})
        return _json(VALID)

    monkeypatch.setattr(service, "call_model", fake_call)
    result = service.enrich({"title": "x"})
    assert result == Enrichment.model_validate(VALID)
    assert len(calls) == 2
    assert "rejected" in calls[1] and "mystery" in calls[1]  # repair carries the error


def test_enrich_quarantines_after_second_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "QUARANTINE_LOG", tmp_path / "quarantine.jsonl")
    calls = []
    monkeypatch.setattr(
        service, "call_model",
        lambda record, extra=None: calls.append(1) or "utter garbage, no braces",
    )
    with pytest.raises(service.QuarantinedError):
        service.enrich({"title": "x", "description": "d", "price_gbp": 1.0})
    assert len(calls) == 2  # one repair retry, no more
    entry = json.loads((tmp_path / "quarantine.jsonl").read_text(encoding="utf-8"))
    assert entry["input"]["title"] == "x"
    assert entry["prompt_version"] == service.PROMPT_VERSION
    assert "raw_output" in entry


# --- endpoint behaviour -----------------------------------------------------

def test_endpoint_returns_422_when_unrepairable(monkeypatch):
    def boom(record):
        raise service.QuarantinedError("schema validation failed: category")

    monkeypatch.setattr(service, "enrich", boom)
    res = _client().post("/enrich", json={"title": "A book"})
    assert res.status_code == 422
    assert "quarantined" in res.json()["error"]


def test_endpoint_rejects_bad_input_before_any_call(monkeypatch):
    calls = []
    monkeypatch.setattr(service, "enrich", lambda record: calls.append(1) or {})
    res = _client().post("/enrich", json={"description": "no title"})
    assert res.status_code == 400
    assert "title" in res.json()["error"]
    assert calls == []  # rejected before the model


# --- Stage 4: retry policy, timeout, kill switch ----------------------------

def test_client_overrides_sdk_defaults(monkeypatch):
    client = service._client()
    assert client.timeout == service.CALL_TIMEOUT_SECONDS == 30.0
    assert client.max_retries == 0  # SDK's silent retries are OFF


def test_retries_on_timeout_then_succeeds(monkeypatch):
    monkeypatch.setattr(service.time, "sleep", lambda seconds: None)
    calls = []
    outcomes = [service.Retriable(Exception("t1")), service.Retriable(Exception("t2"))]

    def flaky(messages, attempt):
        calls.append(attempt)
        if outcomes:
            raise outcomes.pop(0)
        return "answer"

    monkeypatch.setattr(service, "_create", flaky)
    assert service._call_with_policy([{"role": "user", "content": "x"}]) == "answer"
    assert calls == [1, 2, 3]  # two retries, no more than MAX_ATTEMPTS


def test_does_not_retry_on_auth_error(monkeypatch):
    monkeypatch.setattr(service.time, "sleep", lambda seconds: None)
    calls = []

    def bad_key(messages, attempt):
        calls.append(attempt)
        raise service.ModelAuthError("401: invalid api key")

    monkeypatch.setattr(service, "_create", bad_key)
    with pytest.raises(service.ModelAuthError):  # NOT ModelUnavailableError: auth is never retried
        service._call_with_policy([{"role": "user", "content": "x"}])
    assert calls == [1]  # one attempt, zero retries


def test_retries_exhausted_becomes_unavailable(monkeypatch):
    monkeypatch.setattr(service.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(service, "_create", lambda m, a: (_ for _ in ()).throw(service.Retriable(Exception("down"))))
    with pytest.raises(service.ModelUnavailableError):
        service._call_with_policy([{"role": "user", "content": "x"}])


def test_backoff_honours_retry_after(monkeypatch):
    assert service._backoff_seconds(1, retry_after=7.0) == 7.0
    assert service._backoff_seconds(1, retry_after=99.0) == 15.0  # capped
    plain = service._backoff_seconds(1, retry_after=None)
    assert 1.0 <= plain <= 1.5  # 1s + jitter
    third = service._backoff_seconds(3, retry_after=None)
    assert 4.0 <= third <= 4.5


def test_kill_switch_returns_503_with_zero_calls(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "false")
    calls = []
    monkeypatch.setattr(service, "enrich", lambda record: calls.append(1) or {})
    res = _client().post("/enrich", json={"title": "A book"})
    assert res.status_code == 503
    assert "kill switch" in res.json()["error"]
    assert calls == []  # zero model calls


def test_endpoint_maps_auth_failure_to_502(monkeypatch):
    def bad(record):
        raise service.ModelAuthError("401")

    monkeypatch.setattr(service, "enrich", bad)
    res = _client().post("/enrich", json={"title": "A book"})
    assert res.status_code == 502


def test_endpoint_maps_unavailable_to_504(monkeypatch):
    def down(record):
        raise service.ModelUnavailableError("timeout after 3 attempts")

    monkeypatch.setattr(service, "enrich", down)
    res = _client().post("/enrich", json={"title": "A book"})
    assert res.status_code == 504
