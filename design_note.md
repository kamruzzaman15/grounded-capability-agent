# Design Note

## Why this shape

The task is a research assistant that plans, uses tools, recovers from failure,
and returns a cited answer. I chose software capability comparison because the
same request naturally requires parsing, multi-step research, evidence
extraction, comparison, citation, and uncertainty handling. Pricing remains an
optional path because pricing pages are volatile and often JavaScript-gated;
the latest evaluation confirms that plan selection is harder than arithmetic.

## Why LangGraph

The control flow has two genuine loops: a gather loop and a verify/revise loop.
LangGraph makes the branch and stopping rules explicit, carries typed state
through every node, and accumulates a readable per-node trace. A plain Python
loop would be sufficient at this scale, but the graph makes retry caps,
clarification, revision, and termination independently inspectable and testable.

The state contains the parsed goal, evidence, scratchpad observations, attempted
actions, comparison cells, pricing findings, audit, trace, and operational
counters. The CLI prints the trace, and the evaluator persists it with the full
run artifact.

## The main design decision: grounding is enforced, not requested

A prompt that says “only use the evidence” is not a guardrail. The generator can
still fabricate a quote or use a real quote for the wrong criterion. I therefore
made grounding structural:

1. A deterministic gate requires the quote to be a normalized substring of the
   cited evidence.
2. A separate reviewer model judges whether the quote entails the requested
   product, criterion, and label.
3. Any rejected cell is deterministically downgraded to `unverified` and loses
   its citation.
4. The final prose is rendered from the post-verification cells, so an earlier
   draft cannot retain a rejected claim or nonexistent citation.

The fourth step was added after live evaluation exposed a consistency bug: the
structured cells were safely downgraded, but the already-written prose still
claimed the old label. Rendering from audited state closes that gap without
another model call.

## Recovery and how it is tested

`fetch_url` returns failures as observations. The action node retries a failed
fetch up to its cap and tells the planner to use an alternative query or source
if retries are exhausted. Duplicate actions are skipped and a no-progress stall
counter prevents an infinite loop.

The live evaluator now consumes the failure specifications in `cases.json`.
Case 2 is configured to inject one Mural timeout when the planner fetches a
matching URL. The latest run never selected a Mural URL, so the failure-detected
assertion correctly failed rather than awarding recovery credit. Case 5 returns
repeated irrelevant search results and asserts bounded termination with
unverified cells.
This is complemented by deterministic mocked tests that exercise retry,
fallback, quotation rejection, entailment rejection, pricing guards, and
clarification without Ollama or network access.

## Evaluation judgment

Each case declares the behavior it expects. The evaluator scores every declared
assertion and fails closed for an unknown assertion rather than silently ignoring
it. Factual cases also report accuracy, hallucination rate, retrieval recall, and
grounding rate. The report includes model configuration, operational statistics,
injected events, and the per-node trace; a JSON artifact preserves the complete
answer, evidence, prices, and audit.

The latest reduced run with Qwen 2.5 14B and Gemma 3 4B passed 2 of 5 active
cases in 65.2 seconds. Case 1 had zero hallucination but only 17% capability
accuracy. Case 2 failed because its configured Mural injection was never
exercised. The pricing case matched ClickUp's expected total but selected an
unsupported Notion price and omitted ClickUp's plan name. These failures
are useful: the evaluator now rejects superficially correct output instead of
awarding a pass because the expected number appeared somewhere.

## Tradeoffs and stopping point

The current system favors safe misses over unsupported assertions. This keeps
hallucination low but can produce many `unverified` cells when the planner does
not cover both products evenly. Grounding also does not yet enforce official
domains or source ownership deterministically. These are more important next
steps than using a larger model.

The highest-value next change would be a coverage matrix keyed by
`(product, criterion)`. It would prevent the planner from choosing `finish` until
each pair had at least one targeted attempt. After that, I would add official
domain validation and deterministic lowest-plan selection. Multi-turn resume,
semantic duplicate detection, conflicting-source analysis, and a browser
fallback remain documented stretch goals rather than partially implemented
features.
