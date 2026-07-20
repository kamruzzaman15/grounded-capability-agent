"""Offline checks for live-eval failure injection and final rendering."""

from evals.run_evals import evaluate_assertions, inject_case_failures
from src import nodes


def test_configured_fetch_failure_is_injected_once(monkeypatch):
    calls = {"n": 0}

    def succeeds(url, *args, **kwargs):
        calls["n"] += 1
        return {"ok": True, "text": "recovered", "url": url}

    monkeypatch.setattr(nodes, "fetch_url", succeeds)
    case = {
        "failure_injection": {
            "tool": "extract_page",
            "url_pattern": "mural",
            "failure_mode": "timeout",
            "failures_before_success": 1,
        }
    }
    with inject_case_failures(case) as events:
        first = nodes.fetch_url("https://mural.example/docs")
        second = nodes.fetch_url("https://mural.example/docs")

    assert not first["ok"] and "injected timeout" in first["error"]
    assert second["ok"] and calls["n"] == 1
    assert len(events) == 1 and events[0]["outcome"] == "injected_timeout"


def test_finalize_replaces_stale_draft_and_citations():
    state = {
        "comparison": {"cells": [{
            "product": "ClickUp",
            "criterion": "official_slack_integration",
            "label": "unverified",
            "citation_id": "",
            "quote": "",
        }]},
        "cost": {},
        "evidence": [],
        "draft": "ClickUp is verified_present [E9]",
    }
    out = nodes.finalize_node(state)

    assert "verified_present" not in out["draft"]
    assert "[E9]" not in out["draft"]
    assert "unverified" in out["draft"]


def test_case_four_assertions_require_observed_recovery():
    case = {
        "id": 4,
        "assertions": {
            "failure_detected": True,
            "retry_count_at_least": 1,
            "different_query_or_source_used": True,
            "no_fabricated_claims": True,
            "run_terminates_within_step_limit": True,
        },
    }
    result = {
        "answer": "answer",
        "final": {"cells": [{
            "product": "Mural", "criterion": "collaboration",
            "label": "unverified", "citation_id": "", "quote": "",
        }], "cost": {}},
        "evidence": [
            {"id": "E1", "source": "https://one", "content": "one"},
            {"id": "E2", "source": "https://two", "content": "two"},
        ],
        "prices": [],
        "trace": ["act: fetch retry 1", "act: search 'fallback' -> 1 results"],
        "stats": {"retries": 1, "steps": 5, "tool_calls": 3},
    }
    events = [{"outcome": "injected_timeout"}]

    checks = evaluate_assertions(case, result, events)
    assert checks and all(checks.values())
