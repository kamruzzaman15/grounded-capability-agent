"""Public entry point. run_agent(goal) drives the graph once and returns the
final structured output, the prose answer, the trace, and cost/latency stats.

An optional seed (products/criteria/team_size/wants_pricing) lets the eval
harness fix the parse step so agent cells line up with the gold key by exact
criterion key. In normal use no seed is passed and the agent parses the goal.
"""

import time

from .config import RECURSION_LIMIT
from .graph import build_graph

_GRAPH = None


def _graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def initial_state(goal, seed=None):
    return {
        "goal": goal,
        "parsed": dict(seed) if seed else {},
        "scratchpad": [],
        "trace": [],
        "evidence": [],
        "seen_actions": [],
        "next_action": {},
        "step": 0,
        "retries": 0,
        "stall": 0,
        "comparison": {"cells": []},
        "prices": [],
        "cost": {},
        "draft": "",
        "audit": {},
        "revisions": 0,
        "clarifying_question": "",
        "final": {},
        "llm_calls": 0,
        "tool_calls": 0,
    }


def run_agent(goal, seed=None):
    t0 = time.time()
    final = _graph().invoke(initial_state(goal, seed),
                            config={"recursion_limit": RECURSION_LIMIT})
    elapsed = round(time.time() - t0, 1)
    return {
        "goal": goal,
        "answer": final["draft"],
        "final": final["final"],
        "evidence": final["evidence"],
        "prices": final["prices"],
        "audit": final["audit"],
        "trace": final["trace"],
        "stats": {
            "llm_calls": final["llm_calls"],
            "tool_calls": final["tool_calls"],
            "steps": final["step"],
            "retries": final["retries"],
            "revisions": final["revisions"],
            "seconds": elapsed,
        },
    }
