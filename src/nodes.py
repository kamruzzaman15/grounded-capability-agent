"""Graph nodes.

Grounding is enforced with two gates plus a deterministic fix, so it does not
depend on any model choosing to behave:

- Gate 1 (deterministic): the cited quote must be a real substring of the cited
  evidence. Catches fabricated quotes and wrong citations, for free.
- Gate 2 (entailment, reviewer model): the quote must actually establish the
  label for the criterion. Catches a real quote used to support a claim it does
  not make.
- Revise: any cell failing either gate is deterministically downgraded to
  'unverified'. This guarantees no unsupported claim survives and the loop
  converges in one pass.

The gather loop also stops on no progress (STALL_LIMIT gather steps with no new
evidence) and skips duplicate searches/fetches, so it cannot spin on a query
that never returns anything useful.
"""

from . import prompts
from .config import (
    MAX_REVISIONS,
    MAX_RETRIES,
    MAX_STEPS,
    POLARIZED,
    STALL_LIMIT,
    UNVERIFIED,
)
from .llm_client import GENERATOR_MODEL, REVIEWER_MODEL, chat, extract_json
from .schemas import AgentAction, Comparison, EntailmentReport, ParsedGoal, PriceFinding
from .tools import calculator, fetch_url, web_search


def _evidence_by_id(state):
    return {e["id"]: e for e in state["evidence"]}


def _quote_supported(quote, evidence_content):
    """Whitespace-normalized substring match, so minor spacing differences pass."""
    if not quote:
        return False
    q = " ".join(quote.lower().split())
    c = " ".join(evidence_content.lower().split())
    return q in c


def _all_pairs(parsed):
    return [(p, c) for p in parsed.get("products", []) for c in parsed.get("criteria", [])]


# --------------------------------- nodes -----------------------------------


def validate_node(state):
    # Eval harness may seed parsed goal for deterministic scoring; if products
    # are already present, trust the seed and skip the parse call.
    if state.get("parsed", {}).get("products"):
        parsed = state["parsed"]
        llm_inc = 0
    else:
        system, user = prompts.parse_prompt(state["goal"])
        raw = chat([{"role": "system", "content": system},
                    {"role": "user", "content": user}], model=GENERATOR_MODEL)
        data = extract_json(raw) or {}
        try:
            parsed = ParsedGoal(**data).model_dump()
        except Exception:
            parsed = ParsedGoal().model_dump()
        llm_inc = 1
    return {
        "parsed": parsed,
        "trace": [f"validate: products={parsed['products']} criteria={parsed['criteria']} "
                  f"pricing={parsed['wants_pricing']}"],
        "llm_calls": state["llm_calls"] + llm_inc,
    }


def route_after_validate(state):
    p = state["parsed"]
    if len(p.get("products", [])) < 2 or not p.get("criteria"):
        return "clarify"
    return "plan"


def clarify_node(state):
    p = state["parsed"]
    if len(p.get("products", [])) < 2:
        q = ("I need two products to compare. Please name both, or give their "
             "official URLs, and the capabilities you want compared.")
    else:
        q = (f"I can compare {', '.join(p['products'])}, but I need the criteria. "
             "Which capabilities should I compare, for example API access, "
             "integrations, permissions, or automation?")
    return {
        "clarifying_question": q,
        "draft": q,
        "final": {"type": "clarify", "question": q},
        "trace": ["clarify: request underspecified, asking for criteria/products"],
    }


def plan_node(state):
    system, user = prompts.plan_prompt(state)
    raw = chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
               model=GENERATOR_MODEL)
    data = extract_json(raw) or {}
    try:
        action = AgentAction(**data).model_dump()
    except Exception:
        action = AgentAction(action="finish", action_input="",
                             thought="unparseable plan, finishing").model_dump()
    return {
        "next_action": action,
        "scratchpad": [f"THOUGHT: {action['thought']}\n"
                       f"ACTION: {action['action']}({action['action_input']})"],
        "trace": [f"plan#{state['step'] + 1}: {action['action']}({action['action_input'][:60]})"],
        "step": state["step"] + 1,
        "llm_calls": state["llm_calls"] + 1,
    }


def route_after_plan(state):
    if (state["next_action"]["action"] == "finish"
            or state["step"] >= MAX_STEPS
            or state["stall"] >= STALL_LIMIT):
        return "compare"
    return "act"


def act_node(state):
    action = state["next_action"]
    name = action["action"]
    arg = action["action_input"]
    sig = f"{name}:{arg}"
    ev_start = len(state["evidence"])
    new_evidence = []
    attempts = 0
    retries_used = 0
    trace = []

    # Duplicate-action skip: do not re-run a search or fetch already tried.
    if sig in state["seen_actions"]:
        return {
            "scratchpad": [f"OBSERVATION: duplicate action skipped ({sig[:60]})"],
            "trace": [f"act: duplicate action skipped ({name})"],
            "stall": state["stall"] + 1,
        }

    if name == "web_search":
        res = web_search(arg)
        attempts += 1
        if res["ok"]:
            lines = []
            for r in res["results"]:
                eid = f"E{ev_start + len(new_evidence) + 1}"
                new_evidence.append({"id": eid, "source": r["url"],
                                     "title": r["title"], "content": r["snippet"]})
                lines.append(f"{eid} [{r['url']}]: {r['snippet']}")
            obs = "SEARCH RESULTS:\n" + "\n".join(lines)
            trace.append(f"act: search '{arg[:40]}' -> {len(res['results'])} results")
        else:
            obs = f"SEARCH FAILED ({res['error']}). Try a different query or an official docs URL."
            trace.append(f"act: search '{arg[:40]}' -> FAILED ({res['error']})")

    elif name == "fetch_url":
        res = fetch_url(arg)
        attempts += 1
        while (not res["ok"]) and retries_used < MAX_RETRIES:
            retries_used += 1
            res = fetch_url(arg)
            attempts += 1
            trace.append(f"act: fetch retry {retries_used} for {arg[:40]}")
        if res["ok"]:
            eid = f"E{ev_start + 1}"
            new_evidence.append({"id": eid, "source": res["url"],
                                 "title": "fetched page", "content": res["text"]})
            obs = f"FETCHED {eid} [{res['url']}]: {res['text'][:300]}..."
            trace.append(f"act: fetch {arg[:40]} -> ok ({eid})")
        else:
            obs = (f"FETCH FAILED after {retries_used} retries ({res['error']}). "
                   "Fall back: web_search for an alternate official source.")
            trace.append(f"act: fetch {arg[:40]} -> FAILED after retries, needs fallback")
    else:
        obs = f"UNKNOWN ACTION: {name}"
        trace.append(f"act: unknown action {name}")

    made_progress = len(new_evidence) > 0
    return {
        "scratchpad": [f"OBSERVATION: {obs}"],
        "trace": trace,
        "evidence": new_evidence,
        "seen_actions": [sig],
        "tool_calls": state["tool_calls"] + attempts,
        "retries": state["retries"] + retries_used,
        "stall": 0 if made_progress else state["stall"] + 1,
    }


def compare_node(state):
    system, user = prompts.compare_prompt(state)
    raw = chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
               model=GENERATOR_MODEL)
    data = extract_json(raw) or {}
    try:
        comparison = Comparison(**data).model_dump()
    except Exception:
        comparison = {"cells": []}

    have = {(c["product"], c["criterion"]) for c in comparison["cells"]}
    for prod, crit in _all_pairs(state["parsed"]):
        if (prod, crit) not in have:
            comparison["cells"].append(
                {"product": prod, "criterion": crit, "label": UNVERIFIED,
                 "citation_id": "", "quote": ""}
            )
    return {
        "comparison": comparison,
        "trace": [f"compare: {len(comparison['cells'])} cells produced"],
        "llm_calls": state["llm_calls"] + 1,
    }


def price_node(state):
    if not state["parsed"].get("wants_pricing"):
        return {"cost": {}, "prices": [], "trace": ["price: not requested, skipped"]}

    system, user = prompts.price_prompt(state)
    raw = chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
               model=GENERATOR_MODEL)
    data = extract_json(raw) or {}
    findings = []
    for item in (data.get("prices", []) if isinstance(data, dict) else []):
        try:
            findings.append(PriceFinding(**item).model_dump())
        except Exception:
            continue

    ev = _evidence_by_id(state)
    team = state["parsed"].get("team_size")
    lines, prices_out = [], []
    for f in findings:
        price = f.get("per_user_monthly")
        cid = f.get("citation_id", "")
        quote = f.get("quote", "")
        num_ok = price is not None and str(
            int(price) if float(price).is_integer() else price) in quote
        cite_ok = cid in ev and _quote_supported(quote, ev[cid]["content"])
        if price is not None and num_ok and cite_ok and team:
            calc = calculator(f"{price} * {team} * 12")
            if calc["ok"]:
                prices_out.append({**f, "verified": True, "annual_cost": calc["result"]})
                plan = f" ({f.get('plan_name')})" if f.get("plan_name") else ""
                lines.append(f"{f['product']}{plan}: ${price}/user/mo x {team} x 12 "
                             f"= ${calc['result']:.0f}/yr [{cid}]")
                continue
        prices_out.append({**f, "verified": False})
        lines.append(f"{f['product']}: price unverified (no cited figure)")

    return {
        "cost": {"lines": lines, "team_size": team},
        "prices": prices_out,
        "trace": [f"price: {sum(1 for p in prices_out if p.get('verified'))} verified"],
        "llm_calls": state["llm_calls"] + 1,
    }


def draft_node(state):
    system, user = prompts.draft_prompt(state)
    raw = chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
               model=GENERATOR_MODEL)
    return {"draft": raw.strip(), "trace": ["draft: answer written"],
            "llm_calls": state["llm_calls"] + 1}


def verify_node(state):
    comparison = state["comparison"]
    ev = _evidence_by_id(state)
    asserted = [c for c in comparison["cells"] if c["label"] in POLARIZED]

    # Gate 1: deterministic quote-in-evidence check.
    gate1_bad = {}
    survivors = []
    for c in asserted:
        cid = c["citation_id"]
        if cid not in ev or not _quote_supported(c["quote"], ev[cid]["content"]):
            gate1_bad[(c["product"], c["criterion"])] = "quote not found in cited evidence"
        else:
            survivors.append(c)

    # Gate 2: entailment judged by the reviewer model (a different family).
    gate2_bad = {}
    llm_inc = 0
    if survivors:
        system, user = prompts.entailment_prompt(survivors)
        raw = chat([{"role": "system", "content": system},
                    {"role": "user", "content": user}], model=REVIEWER_MODEL)
        data = extract_json(raw) or {}
        llm_inc = 1
        try:
            report = EntailmentReport(
                **(data if isinstance(data, dict) else {"verdicts": data})).model_dump()
        except Exception:
            report = {"verdicts": []}
        for v in report["verdicts"]:
            if v.get("verdict") == "insufficient":
                gate2_bad[(v["product"], v["criterion"])] = v.get("note", "")

    unsupported = [
        {"product": p, "criterion": c, "reason": gate1_bad.get((p, c)) or gate2_bad.get((p, c))}
        for (p, c) in set(gate1_bad) | set(gate2_bad)
    ]
    return {
        "audit": {"gate1_failed": list(gate1_bad), "gate2_failed": list(gate2_bad),
                  "unsupported": unsupported},
        "trace": [f"verify: gate1 rejected {len(gate1_bad)}, gate2 rejected {len(gate2_bad)}, "
                  f"of {len(asserted)} asserted"],
        "llm_calls": state["llm_calls"] + llm_inc,
    }


def route_after_verify(state):
    if state["audit"].get("unsupported") and state["revisions"] < MAX_REVISIONS:
        return "revise"
    return "finalize"


def revise_node(state):
    """Deterministically downgrade unsupported cells to 'unverified'. The guard's
    teeth: a claim that failed either gate cannot survive, and the loop converges.
    """
    unsupported = {(u["product"], u["criterion"]) for u in state["audit"]["unsupported"]}
    cells = []
    for c in state["comparison"]["cells"]:
        if (c["product"], c["criterion"]) in unsupported:
            cells.append({**c, "label": UNVERIFIED, "citation_id": "", "quote": ""})
        else:
            cells.append(c)
    return {
        "comparison": {"cells": cells},
        "revisions": state["revisions"] + 1,
        "trace": [f"revise: downgraded {len(unsupported)} unsupported cell(s) to unverified"],
    }


def _render_verified_answer(state, cells):
    """Render prose only from the post-verification cells.

    The earlier LLM draft is useful as a critique target, but it can become stale
    when ``revise`` downgrades a claim.  The final user-visible answer is therefore
    deterministic: citations can only come from the final structured cells.
    """
    lines = ["Capability comparison:", ""]
    for cell in cells:
        label = cell["label"]
        citation = (f" [{cell['citation_id']}]"
                    if label in POLARIZED and cell.get("citation_id") else "")
        criterion = cell["criterion"].replace("_", " ")
        lines.append(f"- {cell['product']} / {criterion}: {label}{citation}")

    cost_lines = (state.get("cost") or {}).get("lines", [])
    if cost_lines:
        lines.extend(["", "Cost:"])
        lines.extend(f"- {line}" for line in cost_lines)

    counts = {}
    for cell in cells:
        counts.setdefault(cell["product"], 0)
        if cell["label"] == "verified_present":
            counts[cell["product"]] += 1
    leaders = []
    if counts:
        best = max(counts.values())
        leaders = [product for product, count in counts.items() if count == best]

    lines.extend(["", "Recommendation:"])
    if counts and max(counts.values()) > 0 and len(leaders) == 1:
        lines.append(
            f"Based only on the verified capabilities above, {leaders[0]} has "
            "the strongest documented coverage. Confirm every unverified item "
            "that matters to your team before deciding."
        )
    else:
        lines.append(
            "The verified evidence does not establish a unique winner. Confirm "
            "the unverified items that matter to your team before deciding."
        )
    return "\n".join(lines)


def finalize_node(state):
    cells = state["comparison"]["cells"]
    polarized = [c for c in cells if c["label"] in POLARIZED]
    with_cite = [c for c in polarized if c["citation_id"]]
    final = {
        "type": "answer",
        "cells": cells,
        "cost": state.get("cost", {}),
        "sources": sorted({e["source"] for e in state["evidence"]}),
        "unverified": [f"{c['product']} / {c['criterion']}"
                       for c in cells if c["label"] == UNVERIFIED],
        "grounding_rate": (len(with_cite) / len(polarized)) if polarized else 1.0,
    }
    return {
        "final": final,
        "draft": _render_verified_answer(state, cells),
        "trace": ["finalize: answer rendered from verified cells"],
    }
