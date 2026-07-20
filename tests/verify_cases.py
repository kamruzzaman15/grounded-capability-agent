"""Offline end-to-end verification of the evaluation cases.

Drives the real LangGraph graph with the LLM and web tools mocked, so control
flow, both grounding gates, the recovery path, the pricing guard, the
no-progress/duplicate guard, and the clarifying behavior are all checked
deterministically without Ollama or network. Runs in CI; run_evals.py runs the
same cases against live models.

Cases are seeded with products/criteria so the parse step is bypassed and cells
line up with the intended keys.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import nodes  # noqa: E402
from src import prompts as P  # noqa: E402
from src.agent import initial_state  # noqa: E402
from src.graph import build_graph  # noqa: E402


def make_chat(scripts):
    plan_idx = {"i": 0}

    def _chat(messages, model=None, temperature=0.0):
        sp = messages[0]["content"]
        if P.TAG_PLAN in sp:
            acts = scripts["plan"]
            a = acts[min(plan_idx["i"], len(acts) - 1)]
            plan_idx["i"] += 1
            return json.dumps(a)
        if P.TAG_COMPARE in sp:
            return json.dumps(scripts["compare"])
        if P.TAG_PRICE in sp:
            return json.dumps(scripts.get("price", {"prices": []}))
        if P.TAG_ENTAIL in sp:
            return json.dumps(scripts.get("entail", {"verdicts": []}))
        if P.TAG_DRAFT in sp:
            return scripts.get("draft", "ANSWER")
        return "{}"

    return _chat


def make_search(mapping, default_result=None):
    def _search(query, max_results=5):
        for key, results in mapping.items():
            if key.lower() in query.lower():
                return {"ok": True, "results": results}
        if default_result is not None:
            return {"ok": True, "results": default_result}
        return {"ok": False, "error": "no results found", "results": []}

    return _search


def make_fetch(fail_urls=()):
    def _fetch(url, max_chars=2500):
        if any(f in url for f in fail_urls):
            return {"ok": False, "error": "timeout", "url": url}
        return {"ok": True, "text": "Product doc text.", "url": url}

    return _fetch


class patched:
    def __init__(self, chat=None, search=None, fetch=None):
        self.vals = {"chat": chat, "web_search": search, "fetch_url": fetch}
        self._orig = {}

    def __enter__(self):
        for name, val in self.vals.items():
            if val is not None:
                self._orig[name] = getattr(nodes, name)
                setattr(nodes, name, val)
        return self

    def __exit__(self, *exc):
        for name, val in self._orig.items():
            setattr(nodes, name, val)


def run(goal, seed):
    return build_graph().invoke(initial_state(goal, seed), config={"recursion_limit": 90})


# --------------------------------- cases -----------------------------------


def case_1():
    seed = {"products": ["Notion", "ClickUp"],
            "criteria": ["public_api_access", "official_slack_integration",
                         "configurable_role_based_permissions"],
            "team_size": 15, "wants_pricing": False}
    scripts = {
        "plan": [{"thought": "n", "action": "web_search", "action_input": "Notion API docs"},
                 {"thought": "c", "action": "web_search", "action_input": "ClickUp API docs"},
                 {"thought": "done", "action": "finish", "action_input": ""}],
        "compare": {"cells": [
            {"product": "Notion", "criterion": "public_api_access", "label": "verified_present",
             "citation_id": "E1", "quote": "Notion offers a public REST API"},
            {"product": "Notion", "criterion": "official_slack_integration", "label": "verified_present",
             "citation_id": "E1", "quote": "Notion has an official Slack integration"},
            {"product": "Notion", "criterion": "configurable_role_based_permissions", "label": "verified_present",
             "citation_id": "E1", "quote": "admins can assign workspace roles"},
            {"product": "ClickUp", "criterion": "public_api_access", "label": "verified_present",
             "citation_id": "E2", "quote": "ClickUp provides a public API"},
            {"product": "ClickUp", "criterion": "official_slack_integration", "label": "verified_present",
             "citation_id": "E2", "quote": "ClickUp has an official Slack integration"},
            {"product": "ClickUp", "criterion": "configurable_role_based_permissions", "label": "verified_present",
             "citation_id": "E2", "quote": "owners can configure custom roles"},
        ]},
    }
    search = make_search({
        "notion": [{"title": "N", "url": "http://notion",
                    "snippet": "Notion offers a public REST API. Notion has an official Slack "
                               "integration. admins can assign workspace roles."}],
        "clickup": [{"title": "C", "url": "http://clickup",
                     "snippet": "ClickUp provides a public API. ClickUp has an official Slack "
                                "integration. owners can configure custom roles."}],
    })
    with patched(chat=make_chat(scripts), search=search):
        f = run("Compare Notion and ClickUp ...", seed)["final"]
    assert f["type"] == "answer" and len(f["cells"]) == 6
    assert all(c["label"] == "verified_present" and c["citation_id"] for c in f["cells"])
    assert f["grounding_rate"] == 1.0 and not f["unverified"]
    return "case 1 normal: 6 grounded cells pass both gates, grounding 100%"


def case_2():
    seed = {"products": ["Asana", "Trello"],
            "criteria": ["built_in_time_tracking", "workload_capacity_view"],
            "team_size": None, "wants_pricing": False}
    scripts = {
        "plan": [{"thought": "a", "action": "web_search", "action_input": "Asana time tracking"},
                 {"thought": "done", "action": "finish", "action_input": ""}],
        "compare": {"cells": [
            {"product": "Asana", "criterion": "built_in_time_tracking", "label": "verified_present",
             "citation_id": "E1", "quote": "Asana has a built-in timer"},
            {"product": "Asana", "criterion": "workload_capacity_view", "label": "verified_present",
             "citation_id": "E1", "quote": "Workload shows team capacity"},
            {"product": "Trello", "criterion": "built_in_time_tracking", "label": "unverified",
             "citation_id": "", "quote": ""},
            {"product": "Trello", "criterion": "workload_capacity_view", "label": "unverified",
             "citation_id": "", "quote": ""},
        ]},
    }
    search = make_search({"asana": [{"title": "A", "url": "http://asana",
                                     "snippet": "Asana has a built-in timer. Workload shows team capacity."}]})
    with patched(chat=make_chat(scripts), search=search):
        f = run("Compare Asana and Trello ...", seed)["final"]
    labels = {c["label"] for c in f["cells"]}
    assert "verified_present" in labels and "unverified" in labels
    assert "verified_unavailable" not in labels  # no absence inferred from silence
    assert all(c["citation_id"] for c in f["cells"] if c["label"] in nodes.POLARIZED)
    return "case 2 present-vs-unverified: Asana cited present, Trello unverified (no silence->absent)"


def case_3():
    # compare fabricates a verified_unavailable whose quote is NOT in evidence;
    # gate 1 must catch it and revise to unverified.
    seed = {"products": ["Linear", "Height"],
            "criteria": ["end_to_end_encryption_of_document_content", "fedramp_authorization"],
            "team_size": 15, "wants_pricing": False}
    scripts = {
        "plan": [{"thought": "s", "action": "web_search", "action_input": "Linear Height docs"},
                 {"thought": "done", "action": "finish", "action_input": ""}],
        "compare": {"cells": [
            {"product": "Linear", "criterion": "end_to_end_encryption_of_document_content",
             "label": "verified_unavailable", "citation_id": "E1",
             "quote": "Linear does not support end-to-end encryption"},  # fabricated
            {"product": "Linear", "criterion": "fedramp_authorization", "label": "unverified",
             "citation_id": "", "quote": ""},
            {"product": "Height", "criterion": "end_to_end_encryption_of_document_content",
             "label": "unverified", "citation_id": "", "quote": ""},
            {"product": "Height", "criterion": "fedramp_authorization", "label": "unverified",
             "citation_id": "", "quote": ""},
        ]},
        "entail": {"verdicts": []},  # even if gate 2 would pass, gate 1 catches it
    }
    search = make_search({"linear": [{"title": "L", "url": "http://linear",
                                      "snippet": "Linear is an issue tracker for software teams."}]})
    with patched(chat=make_chat(scripts), search=search):
        out = run("Compare Linear and Height ...", seed)
    f = out["final"]
    for c in f["cells"]:
        assert not (c["label"] in nodes.POLARIZED and not c["citation_id"])
    hall = next(c for c in f["cells"] if c["product"] == "Linear"
                and c["criterion"].startswith("end_to_end"))
    assert hall["label"] == "unverified" and out["revisions"] >= 1
    return "case 3 undocumented: fabricated verified_unavailable caught by gate 1, downgraded"


def case_3_gate2():
    # quote IS a substring (gate 1 passes) but does NOT entail the label;
    # gate 2 (entailment reviewer) must catch it.
    seed = {"products": ["Linear", "Height"], "criteria": ["fedramp_authorization"],
            "team_size": 15, "wants_pricing": False}
    scripts = {
        "plan": [{"thought": "s", "action": "web_search", "action_input": "Linear security"},
                 {"thought": "done", "action": "finish", "action_input": ""}],
        "compare": {"cells": [
            {"product": "Linear", "criterion": "fedramp_authorization", "label": "verified_present",
             "citation_id": "E1", "quote": "Linear takes security seriously"},  # real quote, no entailment
            {"product": "Height", "criterion": "fedramp_authorization", "label": "unverified",
             "citation_id": "", "quote": ""},
        ]},
        "entail": {"verdicts": [
            {"product": "Linear", "criterion": "fedramp_authorization",
             "verdict": "insufficient", "note": "quote is generic, not FedRAMP"}]},
    }
    search = make_search({"linear": [{"title": "L", "url": "http://linear",
                                      "snippet": "Linear takes security seriously and encrypts data."}]})
    with patched(chat=make_chat(scripts), search=search):
        out = run("Compare Linear and Height on fedramp ...", seed)
    cell = next(c for c in out["final"]["cells"] if c["product"] == "Linear")
    assert cell["label"] == "unverified" and out["revisions"] >= 1
    return "case 3 gate2: real-but-non-entailing quote caught by entailment gate, downgraded"


def case_4():
    seed = {"products": ["Miro", "Mural"],
            "criteria": ["real_time_collaboration", "official_slack_integration"],
            "team_size": None, "wants_pricing": False}
    scripts = {
        "plan": [{"thought": "fetch", "action": "fetch_url", "action_input": "http://mural/docs"},
                 {"thought": "fallback", "action": "web_search", "action_input": "Mural Slack official"},
                 {"thought": "miro", "action": "web_search", "action_input": "Miro collaboration"},
                 {"thought": "done", "action": "finish", "action_input": ""}],
        "compare": {"cells": [
            {"product": "Mural", "criterion": "real_time_collaboration", "label": "verified_present",
             "citation_id": "E1", "quote": "Mural offers real-time collaboration"},
            {"product": "Mural", "criterion": "official_slack_integration", "label": "unverified",
             "citation_id": "", "quote": ""},
            {"product": "Miro", "criterion": "real_time_collaboration", "label": "verified_present",
             "citation_id": "E2", "quote": "Miro supports real-time collaboration"},
            {"product": "Miro", "criterion": "official_slack_integration", "label": "unverified",
             "citation_id": "", "quote": ""},
        ]},
    }
    search = make_search({
        "mural": [{"title": "Mural", "url": "http://mural",
                   "snippet": "Mural offers real-time collaboration."}],
        "miro": [{"title": "Miro", "url": "http://miro",
                  "snippet": "Miro supports real-time collaboration."}],
    })
    fetch = make_fetch(fail_urls=["mural/docs"])
    with patched(chat=make_chat(scripts), search=search, fetch=fetch):
        out = run("Compare Miro and Mural ...", seed)
    f = out["final"]
    assert out["retries"] >= 1
    assert any("FAILED" in t for t in out["trace"])
    assert any("fallback" in t.lower() or "search" in t.lower() for t in out["trace"])
    for c in f["cells"]:
        assert not (c["label"] in nodes.POLARIZED and not c["citation_id"])
    assert any(c["label"] == "verified_present" and c["citation_id"] for c in f["cells"])
    return "case 4 extraction failure: retried, fell back, recovered, nothing fabricated"


def case_5():
    seed = {"products": ["Notion", "ClickUp"], "criteria": ["collaboration_capabilities"],
            "team_size": 20, "wants_pricing": True}
    scripts = {
        "plan": [{"thought": "n", "action": "web_search", "action_input": "Notion pricing"},
                 {"thought": "c", "action": "web_search", "action_input": "ClickUp pricing"},
                 {"thought": "done", "action": "finish", "action_input": ""}],
        "compare": {"cells": [
            {"product": "Notion", "criterion": "collaboration_capabilities", "label": "verified_present",
             "citation_id": "E1", "quote": "Notion supports real-time collaboration"},
            {"product": "ClickUp", "criterion": "collaboration_capabilities", "label": "verified_present",
             "citation_id": "E2", "quote": "ClickUp offers collaborative docs"},
        ]},
        "price": {"prices": [
            {"product": "Notion", "per_user_monthly": 10, "plan_name": "Plus", "citation_id": "E1",
             "quote": "Notion Plus is $10 per member per month billed yearly"},
            {"product": "ClickUp", "per_user_monthly": 7, "plan_name": "Unlimited", "citation_id": "E2",
             "quote": "ClickUp Unlimited is $7 per user per month billed yearly"},
        ]},
    }
    search = make_search({
        "notion": [{"title": "N", "url": "http://notion",
                    "snippet": "Notion supports real-time collaboration. Notion Plus is $10 per "
                               "member per month billed yearly."}],
        "clickup": [{"title": "C", "url": "http://clickup",
                     "snippet": "ClickUp offers collaborative docs. ClickUp Unlimited is $7 per "
                                "user per month billed yearly."}],
    })
    with patched(chat=make_chat(scripts), search=search):
        f = run("Compare Notion and ClickUp collaboration + cost ...", seed)["final"]
    lines = " ".join(f["cost"]["lines"])
    assert "2400" in lines and "1680" in lines, lines  # 10*20*12 and 7*20*12
    assert all(c["citation_id"] for c in f["cells"])
    return "case 5 pricing: calc matches cited figures (2400, 1680), collaboration cells grounded"


def case_5_guard():
    seed = {"products": ["Notion", "ClickUp"], "criteria": ["collaboration_capabilities"],
            "team_size": 20, "wants_pricing": True}
    scripts = {
        "plan": [{"thought": "n", "action": "web_search", "action_input": "Notion pricing"},
                 {"thought": "done", "action": "finish", "action_input": ""}],
        "compare": {"cells": [
            {"product": "Notion", "criterion": "collaboration_capabilities", "label": "unverified",
             "citation_id": "", "quote": ""},
            {"product": "ClickUp", "criterion": "collaboration_capabilities", "label": "unverified",
             "citation_id": "", "quote": ""},
        ]},
        "price": {"prices": [
            {"product": "Notion", "per_user_monthly": 10, "plan_name": "Plus", "citation_id": "E1",
             "quote": "Notion has great collaboration"}]},  # no '10' in quote -> unverified
    }
    search = make_search({"notion": [{"title": "N", "url": "http://n",
                                      "snippet": "Notion has great collaboration"}]})
    with patched(chat=make_chat(scripts), search=search):
        f = run("Compare ... cost ...", seed)["final"]
    assert "unverified" in " ".join(f["cost"]["lines"]).lower()
    return "case 5 guard: uncited price reported unverified, not computed"


def case_6():
    seed = {"products": ["Notion", "ClickUp"], "criteria": [],
            "team_size": None, "wants_pricing": False}
    with patched(chat=make_chat({"plan": []})):
        out = run("Which is better, Notion or ClickUp?", seed)
    f = out["final"]
    assert f["type"] == "clarify" and f["question"] and "cells" not in f
    return "case 6 underspecified: asked a clarifying question, no comparison (resume is a known gap)"


def case_7():
    seed = {"products": ["Figma", "Canva"],
            "criteria": ["developer_api_access", "version_history", "configurable_team_permissions"],
            "team_size": None, "wants_pricing": False}
    scripts = {
        "plan": [{"thought": "f", "action": "web_search", "action_input": "Figma docs"},
                 {"thought": "c", "action": "web_search", "action_input": "Canva docs"},
                 {"thought": "done", "action": "finish", "action_input": ""}],
        "compare": {"cells": [
            {"product": "Figma", "criterion": "developer_api_access", "label": "verified_present",
             "citation_id": "E1", "quote": "Figma has a REST API"},
            {"product": "Figma", "criterion": "version_history", "label": "verified_present",
             "citation_id": "E1", "quote": "Figma has version history"},
            {"product": "Figma", "criterion": "configurable_team_permissions", "label": "verified_present",
             "citation_id": "E1", "quote": "Figma team permissions define roles"},
            {"product": "Canva", "criterion": "developer_api_access", "label": "verified_present",
             "citation_id": "E2", "quote": "Canva Connect APIs let you integrate"},
            {"product": "Canva", "criterion": "version_history", "label": "verified_present",
             "citation_id": "E2", "quote": "Canva can restore older versions"},
            {"product": "Canva", "criterion": "configurable_team_permissions", "label": "verified_present",
             "citation_id": "E2", "quote": "Canva has roles and permissions controls"},
        ]},
    }
    search = make_search({
        "figma": [{"title": "F", "url": "http://figma",
                   "snippet": "Figma has a REST API. Figma has version history. Figma team "
                              "permissions define roles."}],
        "canva": [{"title": "C", "url": "http://canva",
                   "snippet": "Canva Connect APIs let you integrate. Canva can restore older "
                              "versions. Canva has roles and permissions controls."}],
    })
    with patched(chat=make_chat(scripts), search=search):
        f = run("Compare Figma and Canva ...", seed)["final"]
    assert len(f["cells"]) == 6
    assert all(c["label"] == "verified_present" and c["citation_id"] for c in f["cells"])
    return "case 7 different category: Figma vs Canva, 6 grounded cells pass both gates"


def case_8():
    seed = {"products": ["Product Alpha", "Product Beta"],
            "criteria": ["quantum_resistant_document_encryption"],
            "team_size": None, "wants_pricing": False}
    scripts = {
        # planner keeps proposing the same search; dedup + stall must stop it
        "plan": [{"thought": "s", "action": "web_search", "action_input": "quantum encryption"},
                 {"thought": "s", "action": "web_search", "action_input": "quantum encryption"},
                 {"thought": "s", "action": "web_search", "action_input": "quantum encryption"},
                 {"thought": "s", "action": "web_search", "action_input": "quantum encryption"}],
        "compare": {"cells": [
            {"product": "Product Alpha", "criterion": "quantum_resistant_document_encryption",
             "label": "unverified", "citation_id": "", "quote": ""},
            {"product": "Product Beta", "criterion": "quantum_resistant_document_encryption",
             "label": "unverified", "citation_id": "", "quote": ""},
        ]},
    }
    # every search returns the same irrelevant page
    search = make_search({"quantum": [{"title": "generic", "url": "https://example.com/generic-security-page",
                                       "snippet": "Generic security overview."}]})
    with patched(chat=make_chat(scripts), search=search):
        out = run("Compare Product Alpha and Product Beta on quantum ...", seed)
    f = out["final"]
    assert all(c["label"] == "unverified" for c in f["cells"])
    assert not any(c["label"] in nodes.POLARIZED for c in f["cells"])
    assert out["tool_calls"] <= 8 and out["step"] <= 12
    return (f"case 8 loop/no-progress: dedup+stall stopped it "
            f"({out['tool_calls']} tool calls, {out['step']} steps), all unverified")


CASES = [case_1, case_2, case_3, case_3_gate2, case_4, case_5, case_5_guard,
         case_6, case_7, case_8]


def main():
    ok = 0
    for fn in CASES:
        try:
            print(f"PASS  {fn()}")
            ok += 1
        except AssertionError as e:
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"ERROR {fn.__name__}: {e}")
    print(f"\n{ok}/{len(CASES)} checks passed")
    return ok == len(CASES)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
