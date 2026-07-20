"""End-to-end evaluation against live Ollama and the live web.

Two tracks:
- behavioral: pass/fail on defined behavior (clarify, refuse, recover, terminate).
- factual: score cells against the dated gold key for capability accuracy,
  hallucination rate, grounding rate, and retrieval recall on answerable cells.

Factual and behavioral non-clarify cases are SEEDED with the case's canonical
products and criteria (from cases.json) so agent cells line up with the gold key
by exact criterion key. Case 6 (known_gap) is seeded with empty criteria so it
must clarify. The parse step is only exercised implicitly; seeding keeps scoring
deterministic, which is standard for an eval harness.

Run:  python evals/run_evals.py    (requires Ollama running + network)
"""

import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import nodes  # noqa: E402
from src.agent import run_agent  # noqa: E402
from src.llm_client import GENERATOR_MODEL, REVIEWER_MODEL  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = json.load(open(os.path.join(HERE, "cases.json")))
GOLD = json.load(open(os.path.join(HERE, "gold_key.json")))
RESULTS_PATH = os.path.join(HERE, "results.md")
ARTIFACTS_PATH = os.path.join(HERE, "run_artifacts.json")

POLARIZED = {"verified_present", "verified_unavailable"}


def norm(s):
    return " ".join(str(s).lower().split())


def seed_for(case):
    wants_pricing = any("cost" in c or "price" in c for c in case.get("criteria", []))
    return {
        "products": case.get("products", []),
        "criteria": case.get("criteria", []),
        "team_size": 20 if wants_pricing else None,
        "wants_pricing": wants_pricing,
    }


def gold_cells(case):
    ref = case.get("gold_key_ref", "")
    key = ref.split(".")[-1] if ref else ""
    entry = GOLD.get(key, {})
    return entry.get("cells", [])


def score_factual(case, result):
    gold = gold_cells(case)
    cells = result["final"].get("cells", [])
    if not gold:  # e.g. case 5 pricing-focused, scored separately below
        return None
    total = correct = hallucinated = recall_hits = recall_denom = 0
    for g in gold:
        total += 1
        got = next((c for c in cells
                    if norm(c["product"]) == norm(g["product"])
                    and norm(c["criterion"]) == norm(g["criterion"])), None)
        got_label = got["label"] if got else "unverified"
        if got_label == g["label"]:
            correct += 1
        if got_label in POLARIZED and got_label != g["label"]:
            hallucinated += 1
        if g["label"] in POLARIZED:
            recall_denom += 1
            if got and got.get("citation_id"):
                recall_hits += 1
    return {
        "capability_accuracy": correct / total,
        "hallucination_rate": hallucinated / total,
        "retrieval_recall": recall_hits / recall_denom if recall_denom else 1.0,
        "grounding_rate": result["final"].get("grounding_rate", 1.0),
    }


def score_pricing(result):
    gold = GOLD.get("case_5", {}).get("pricing", [])
    lines = " ".join(result["final"].get("cost", {}).get("lines", []))
    hits = 0
    for g in gold:
        if str(int(g["expected_annual_cost_usd"])) in lines:
            hits += 1
    return {"pricing_cells": len(gold), "pricing_cost_matches": hits}


def check_behavioral(case, result):
    final = result["final"]
    if case.get("expect_clarify"):
        return final.get("type") == "clarify" and bool(final.get("question"))
    # no polarized claim may lack a citation, ever
    for c in final.get("cells", []):
        if c["label"] in POLARIZED and not c.get("citation_id"):
            return False
    if case["id"] == 8:  # loop / no-progress: everything unverified, caps held
        all_unverified = all(c["label"] == "unverified" for c in final.get("cells", []))
        within = (result["stats"]["tool_calls"] <= case["limits"]["max_total_tool_calls"]
                  and result["stats"]["steps"] <= case["limits"]["max_graph_steps"])
        return all_unverified and within
    return True


@contextmanager
def inject_case_failures(case):
    """Apply the deterministic failure requested by a case, then restore tools."""
    spec = case.get("failure_injection") or {}
    events = []
    original_fetch = nodes.fetch_url
    original_search = nodes.web_search

    if spec.get("tool") == "extract_page":
        pattern = spec.get("url_pattern", "").lower()
        failures_before_success = int(spec.get("failures_before_success", 1))
        attempts = {"failed": 0}

        def injected_fetch(url, *args, **kwargs):
            if pattern in url.lower() and attempts["failed"] < failures_before_success:
                attempts["failed"] += 1
                events.append({
                    "tool": "fetch_url", "target": url,
                    "outcome": f"injected_{spec.get('failure_mode', 'failure')}",
                    "attempt": attempts["failed"],
                })
                return {"ok": False,
                        "error": f"injected {spec.get('failure_mode', 'failure')}",
                        "url": url}
            return original_fetch(url, *args, **kwargs)

        nodes.fetch_url = injected_fetch

    if spec.get("tool") == "search_web" and spec.get("mode") == "repeated_irrelevant_results":
        urls = spec.get("returned_urls", []) or ["https://example.com/irrelevant"]

        def injected_search(query, max_results=5):
            events.append({
                "tool": "web_search", "target": query,
                "outcome": "injected_irrelevant_results",
            })
            results = [{
                "title": "Injected generic security result",
                "snippet": ("Generic security information with no statement about "
                            "either requested product or capability."),
                "url": url,
            } for url in urls[:max_results]]
            return {"ok": True, "results": results}

        nodes.web_search = injected_search

    try:
        yield events
    finally:
        nodes.fetch_url = original_fetch
        nodes.web_search = original_search


def _evidence_by_id(result):
    return {item["id"]: item for item in result.get("evidence", [])}


def _quote_in_evidence(quote, content):
    q = " ".join(str(quote).lower().split())
    c = " ".join(str(content).lower().split())
    return bool(q) and q in c


def _all_polarized_grounded(result):
    evidence = _evidence_by_id(result)
    for cell in result["final"].get("cells", []):
        if cell["label"] not in POLARIZED:
            continue
        cited = evidence.get(cell.get("citation_id"))
        if not cited or not _quote_in_evidence(cell.get("quote", ""), cited["content"]):
            return False
    return True


def _cells_match_gold(case, result):
    gold = gold_cells(case)
    cells = result["final"].get("cells", [])
    if not gold or len(cells) != len(gold):
        return False
    for expected in gold:
        got = next((cell for cell in cells
                    if norm(cell["product"]) == norm(expected["product"])
                    and norm(cell["criterion"]) == norm(expected["criterion"])), None)
        if not got or got["label"] != expected["label"]:
            return False
    return True


def evaluate_assertions(case, result, injection_events):
    """Evaluate every assertion declared by the case; unknown checks fail closed."""
    cells = result["final"].get("cells", [])
    trace = result.get("trace", [])
    prices = result.get("prices", [])
    cost_lines = result["final"].get("cost", {}).get("lines", [])
    grounded = _all_polarized_grounded(result)
    gold = gold_cells(case)
    gold_unverified = {(norm(g["product"]), norm(g["criterion"])) for g in gold
                       if g["label"] == "unverified"}
    got_by_pair = {(norm(c["product"]), norm(c["criterion"])): c for c in cells}
    verified_prices = [price for price in prices if price.get("verified")]
    pricing_gold = GOLD.get("case_5", {}).get("pricing", [])
    checks = {}

    for name in case.get("assertions", {}):
        if name == "all_cells_match_gold":
            value = _cells_match_gold(case, result)
        elif name in {"all_polarized_cells_have_quote", "quote_must_entail_label",
                      "all_final_claims_grounded", "no_fabricated_claims"}:
            value = grounded
        elif name == "recommendation_must_follow_priority":
            value = _cells_match_gold(case, result) and "recommendation:" in result["answer"].lower()
        elif name == "no_absence_inferred_from_silence":
            value = all(got_by_pair.get(pair, {}).get("label") != "verified_unavailable"
                        for pair in gold_unverified)
        elif name == "all_unresolved_cells_marked_unverified":
            value = bool(cells) and all(c["label"] == "unverified" for c in cells)
        elif name == "no_present_or_unavailable_without_quote":
            value = grounded
        elif name == "absence_of_evidence_not_treated_as_absence":
            value = all(c["label"] != "verified_unavailable" for c in cells)
        elif name == "failure_detected":
            value = bool(injection_events) and any("injected_" in e["outcome"]
                                                   for e in injection_events)
        elif name == "retry_count_at_least":
            value = result["stats"]["retries"] >= 1
        elif name == "different_query_or_source_used":
            sources = {e["source"] for e in result.get("evidence", [])}
            searches = {entry for entry in trace if entry.startswith("act: search")}
            value = len(sources) >= 2 or len(searches) >= 2
        elif name == "run_terminates_within_step_limit":
            value = result["stats"]["steps"] <= case.get("limits", {}).get("max_graph_steps", 12)
        elif name == "price_has_supporting_quote":
            value = (len(verified_prices) == len(pricing_gold)
                     and all(p.get("citation_id") and p.get("quote") for p in verified_prices))
        elif name == "billing_frequency_identified":
            value = (len(verified_prices) == len(pricing_gold)
                     and all("year" in (p.get("quote", "") + " " + " ".join(cost_lines)).lower()
                             or "/yr" in " ".join(cost_lines).lower()
                             for p in verified_prices))
        elif name == "plan_name_identified":
            value = (len(verified_prices) == len(pricing_gold)
                     and all(p.get("plan_name") for p in verified_prices))
        elif name == "calculation_matches_cited_price":
            value = score_pricing(result)["pricing_cost_matches"] == len(pricing_gold)
        elif name == "calculator_tool_used":
            value = bool(verified_prices) and all("annual_cost" in p for p in verified_prices)
        elif name == "unverified_if_price_cannot_be_confirmed":
            value = all(p.get("verified") or "annual_cost" not in p for p in prices)
        elif name == "asks_clarifying_question":
            value = result["final"].get("type") == "clarify" and bool(result["final"].get("question"))
        elif name == "does_not_start_research":
            value = result["stats"]["tool_calls"] == 0 and not result.get("evidence")
        elif name == "does_not_make_recommendation":
            value = result["final"].get("type") == "clarify"
        elif name == "criterion_marked_unverified":
            value = bool(cells) and all(c["label"] == "unverified" for c in cells)
        elif name == "no_present_or_unavailable_claim":
            value = all(c["label"] == "unverified" for c in cells)
        elif name == "tool_calls_within_limit":
            value = result["stats"]["tool_calls"] <= case["limits"]["max_total_tool_calls"]
        elif name == "graph_steps_within_limit":
            value = result["stats"]["steps"] <= case["limits"]["max_graph_steps"]
        elif name == "run_terminates":
            value = bool(result.get("final"))
        else:
            value = False
        checks[name] = bool(value)
    return checks


def artifact_for(case, result, outcome, assertions, metrics, pricing, injection_events):
    """Keep the complete inspectable output, including the per-node trace."""
    return {
        "case_id": case["id"],
        "track": case["track"],
        "status": case.get("status", "active"),
        "outcome": outcome,
        "input": case["input"],
        "assertions": assertions,
        "metrics": metrics,
        "pricing": pricing,
        "injection_events": injection_events,
        "answer": result["answer"],
        "final": result["final"],
        "evidence": result["evidence"],
        "prices": result.get("prices", []),
        "audit": result.get("audit", {}),
        "trace": result["trace"],
        "stats": result["stats"],
    }


def append_trace(lines, trace):
    """Add a readable trace to the Markdown summary."""
    lines.append("- Trace:")
    if not trace:
        lines.append("  - (no trace entries)")
        return
    for entry in trace:
        # Indent continuation lines so one trace entry remains one Markdown item.
        safe_entry = str(entry).replace("\n", "\n    ")
        lines.append(f"  - {safe_entry}")


def main():
    generated_at = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Evaluation Results",
        "",
        f"- Generated: {generated_at}",
        f"- Generator: `{GENERATOR_MODEL}`",
        f"- Reviewer: `{REVIEWER_MODEL}`",
        "",
    ]
    artifacts = []
    for case in CASES:
        cid, track, status = case["id"], case["track"], case.get("status", "active")
        label = f"[{cid}] {status}/{track}"
        if status == "known_gap":
            label += " (clarify-only; resume is a documented gap)"
        print(label + ": " + (case.get("input", "multi-turn"))[:60])
        try:
            seed = None if case.get("expect_clarify") else seed_for(case)
            # for clarify case, seed products but empty criteria so it clarifies
            if case.get("expect_clarify"):
                seed = {"products": case.get("products", []), "criteria": [],
                        "team_size": None, "wants_pricing": False}
            with inject_case_failures(case) as injection_events:
                result = run_agent(case["input"], seed=seed)

            metrics = score_factual(case, result) if track == "factual" else None
            pricing = score_pricing(result) if cid == 5 else None
            assertions = evaluate_assertions(case, result, injection_events)
            passed = bool(assertions) and all(assertions.values())
            outcome = "PASS" if passed else "FAIL"

            console_details = []
            if metrics:
                console_details.append(
                    f"acc={metrics['capability_accuracy']:.0%} "
                    f"halluc={metrics['hallucination_rate']:.0%} "
                    f"recall={metrics['retrieval_recall']:.0%} "
                    f"ground={metrics['grounding_rate']:.0%}"
                )
            if pricing:
                console_details.append(
                    f"pricing={pricing['pricing_cost_matches']}/{pricing['pricing_cells']}"
                )
            failed_count = sum(not value for value in assertions.values())
            console_details.append(f"assertions={len(assertions) - failed_count}/{len(assertions)}")
            print(f"    {outcome}  " + " ".join(console_details))

            lines.extend([
                f"## Case {cid} — {outcome}",
                "",
                f"- Track: `{track}`",
                f"- Status: `{status}`",
            ])
            if metrics:
                lines.append(
                    f"- Metrics: accuracy {metrics['capability_accuracy']:.0%}, "
                    f"hallucination {metrics['hallucination_rate']:.0%}, "
                    f"retrieval recall {metrics['retrieval_recall']:.0%}, "
                    f"grounding {metrics['grounding_rate']:.0%}"
                )
            if pricing:
                lines.append(
                    f"- Pricing: {pricing['pricing_cost_matches']}/{pricing['pricing_cells']} "
                    "expected annual costs matched"
                )

            s = result["stats"]
            lines.append(f"- Stats: {s['llm_calls']} LLM, {s['tool_calls']} tool, "
                         f"{s['steps']} steps, {s['retries']} retries, {s['seconds']}s")
            if injection_events:
                lines.append(f"- Injected failures/results: {len(injection_events)}")
            lines.extend(["- Assertions:"])
            for assertion, ok in assertions.items():
                lines.append(f"  - {'PASS' if ok else 'FAIL'} — `{assertion}`")
            append_trace(lines, result.get("trace", []))
            lines.append("")
            artifacts.append(artifact_for(
                case, result, outcome, assertions, metrics, pricing, injection_events
            ))
        except Exception as e:  # noqa: BLE001
            print(f"    ERROR: {e}")
            lines.extend([f"## Case {cid} — ERROR", "", f"- Error: {e}", ""])
            artifacts.append({
                "case_id": cid,
                "track": track,
                "status": status,
                "input": case.get("input", ""),
                "error": str(e),
            })

    with open(RESULTS_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    artifact_document = {
        "generated_at": generated_at,
        "generator_model": GENERATOR_MODEL,
        "reviewer_model": REVIEWER_MODEL,
        "cases": artifacts,
    }
    with open(ARTIFACTS_PATH, "w") as f:
        json.dump(artifact_document, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("\nWrote results.md and run_artifacts.json")


if __name__ == "__main__":
    main()
