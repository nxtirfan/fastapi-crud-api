"""Run the eight labelled eval cases against the running /enrich endpoint.

Usage:
    python evals/run_evals.py [base_url]

Default base_url: http://localhost:8010 (this machine's port for the Task API;
the compose stack serves 8000). The endpoint must be running WITHOUT LLM_STUB
so the score reflects the real model, not the stub.

Prints the percentage on the key field (category), and every failure with the
model's answer, so the next prompt change can be judged honestly.
"""

import json
import sys
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8010"
CASES = Path(__file__).resolve().parent / "cases.json"


def enrich(record: dict) -> dict:
    """POST one record; return (status, body) without raising on 4xx/5xx."""
    payload = json.dumps(record).encode("utf-8")
    req = urlrequest.Request(
        BASE_URL + "/enrich",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=180) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            pass
        return exc.code, body


def main() -> None:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    print(f"Running {len(cases)} eval cases against {BASE_URL}/enrich ...")
    passed, failures = 0, []
    for i, case in enumerate(cases, start=1):
        record = {k: case[k] for k in ("title", "description", "price_gbp")}
        status, body = enrich(record)
        if status == 200:
            got = body.get("category")
        else:
            got = f"HTTP {status}: {body}"
        ok = got == case["expected_category"]
        passed += ok
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] case {i}: {case['title'][:50]} -> expected "
              f"{case['expected_category']}, got {got} "
              f"(note: {case['note'][:60]})")
        if not ok:
            failures.append((case, got))
    print()
    print(f"Score: {passed}/{len(cases)} ({passed / len(cases):.0%}) on category.")
    if failures:
        print("Failures:")
        for case, got in failures:
            print(f"  - {case['title']}: expected {case['expected_category']}, got {got}")


if __name__ == "__main__":
    main()
