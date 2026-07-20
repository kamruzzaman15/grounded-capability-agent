"""Recovery tests for the act node: a failing fetch is retried in-node up to the
cap, then the observation instructs the planner to fall back. Duplicate actions
are skipped. Uses mocked tools, no network.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import nodes  # noqa: E402
from src.config import MAX_RETRIES  # noqa: E402


def _state(action, seen=None):
    return {
        "goal": "g", "parsed": {}, "scratchpad": [], "trace": [], "evidence": [],
        "seen_actions": seen or [], "next_action": action, "step": 1, "retries": 0,
        "stall": 0, "comparison": {"cells": []}, "prices": [], "cost": {}, "draft": "",
        "audit": {}, "revisions": 0, "clarifying_question": "", "final": {},
        "llm_calls": 0, "tool_calls": 0,
    }


def test_fetch_retries_then_signals_fallback(monkeypatch):
    calls = {"n": 0}

    def always_fail(url, max_chars=2500):
        calls["n"] += 1
        return {"ok": False, "error": "403", "url": url}

    monkeypatch.setattr(nodes, "fetch_url", always_fail)
    out = nodes.act_node(_state({"action": "fetch_url", "action_input": "http://x"}))
    assert calls["n"] == 1 + MAX_RETRIES
    assert out["retries"] == MAX_RETRIES
    assert out["tool_calls"] == 1 + MAX_RETRIES
    assert "FETCH FAILED" in out["scratchpad"][0] and "web_search" in out["scratchpad"][0]


def test_fetch_recovers_on_retry(monkeypatch):
    calls = {"n": 0}

    def fail_then_ok(url, max_chars=2500):
        calls["n"] += 1
        return ({"ok": False, "error": "timeout", "url": url} if calls["n"] == 1
                else {"ok": True, "text": "Product X has a public REST API.", "url": url})

    monkeypatch.setattr(nodes, "fetch_url", fail_then_ok)
    out = nodes.act_node(_state({"action": "fetch_url", "action_input": "http://x"}))
    assert out["retries"] == 1 and len(out["evidence"]) == 1
    assert "REST API" in out["evidence"][0]["content"]


def test_duplicate_action_is_skipped():
    out = nodes.act_node(_state({"action": "web_search", "action_input": "same query"},
                                seen=["web_search:same query"]))
    assert "duplicate" in out["scratchpad"][0].lower()
    assert out["stall"] == 1
    assert "tool_calls" not in out  # no tool ran


if __name__ == "__main__":
    class MP:
        def __init__(self):
            self._o = []

        def setattr(self, obj, name, val):
            self._o.append((obj, name, getattr(obj, name)))
            setattr(obj, name, val)

        def undo(self):
            for obj, name, val in reversed(self._o):
                setattr(obj, name, val)

    for t in ["test_fetch_retries_then_signals_fallback", "test_fetch_recovers_on_retry"]:
        mp = MP()
        globals()[t](mp)
        mp.undo()
        print(f"PASS {t}")
    test_duplicate_action_is_skipped()
    print("PASS test_duplicate_action_is_skipped")
    print("recovery tests OK")
