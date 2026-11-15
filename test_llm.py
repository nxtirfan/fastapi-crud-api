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
