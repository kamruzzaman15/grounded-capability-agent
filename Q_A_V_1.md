# Interview Prep: Likely Questions & Answers

Prep notes for the take-home follow-up interview. Organized around the two
things the exercise says they'll probe: **why each component**, and **depth**
(what breaks, what I'd harden, what I cut). Answers are grounded in the actual
code (`src/`, `evals/`), not aspirational.

---

## 1. Why each component

### Why LangGraph instead of a plain Python while-loop?
There are two genuine loops in this system, not one: a **gather loop**
(plan → act → plan...) and a **verify/revise loop** (draft → verify → revise →
verify...). A hand-rolled loop would work at this scale, but LangGraph makes
the stopping conditions — step cap, stall cap, revision cap — into named,
independently unit-testable routing functions (`route_after_plan`,
`route_after_verify` in `src/nodes.py`) instead of `if` statements buried
inside a monolithic loop body. It also gives me typed state with reducers
(`operator.add` on `evidence`/`trace`/`scratchpad`) so every node returns only
its delta, and a free per-node trace for observability. I'd defend this as
"the graph made the control flow inspectable," not "LangGraph is required at
this scale" — it isn't.

### Why two different model families for generator vs. reviewer?
`qwen2.5:14b` writes the comparison; `gemma3:4b` audits it in the verify
step. If the same model (or family) did both, a systematic mistake the writer
makes — e.g. treating a promotional blurb as proof of a capability — is
likely to be a mistake the same model *doesn't catch in itself* when asked to
re-check, because it shares the same blind spots. A different family is a
cheap way to decorrelate the writer's and the auditor's failure modes. It's
not a proof of independence, just a reasonable bet.

### Why the two-gate grounding design instead of a "please only use the evidence" prompt?
Because a prompt instruction is not a guardrail — it's a request the model can
ignore under distribution shift. Grounding here is structural:
1. **Gate 1 (deterministic):** the cited quote must be a whitespace-normalized
   substring of the cited evidence (`_quote_supported` in `src/nodes.py`).
   Catches fabricated quotes and mismatched citation IDs for free, no model
   call needed.
2. **Gate 2 (entailment, reviewer model):** given only the quote, does it
   actually establish the stated label for that product/criterion? Catches a
   *real* quote being misused to support a claim it doesn't make.
3. Anything either gate rejects is deterministically downgraded to
   `unverified` in `revise_node` — not re-argued, just downgraded. The loop
   provably converges in one revision pass because the downgraded cells leave
   the `POLARIZED` set and can't be re-flagged.
4. The **final prose is rendered from the post-verification cells**
   (`_render_verified_answer`), not from the earlier LLM draft. This was a bug
   I actually hit: an early version downgraded a cell in `revise` but the
   already-written prose still asserted the old label, because it was drafted
   before verification ran. Rendering from audited state instead of trusting
   stale prose closed that gap without another model call.

### Why three labels (`verified_present` / `verified_unavailable` / `unverified`) instead of true/false?
Because "the search didn't find it" is not evidence that a capability is
absent — it's evidence the search was incomplete. Collapsing to a boolean
forces the model to guess on every gap. The third state, `unverified`, is the
honest default and is what protects the hallucination-rate metric: in every
scored eval run, hallucination rate was 0% because a cell can only assert a
polarity when it survives both gates; otherwise it degrades to "I don't know,"
not to a guessed "no."

### Why DuckDuckGo (no API key) + requests/BeautifulSoup instead of a paid search API or a RAG/vector-store pipeline?
Cost and setup friction — the brief says keep costs low and a cheap
model/tool stack is fine. A vector store would be the wrong tool here anyway:
this isn't retrieval over a fixed corpus, it's live web research with a
paginated action loop, so a ReAct-style search+fetch tool pair fits the task
shape better than an embeddings index. The tradeoff I accepted: DuckDuckGo
scraping has no uptime/rate-limit contract and its snippets are sometimes
shallow, which is a real factor in the retrieval-coverage misses in cases 1
and 7 (see §3).

### Why an AST-restricted calculator instead of `eval()` or a code-execution sandbox?
`src/tools.py`'s `_eval_node` walks a parsed AST and only permits numeric
constants and arithmetic binary/unary ops — no names, calls, attributes, or
imports. `eval()` on model-generated strings is a straightforward code-
execution vector; a full sandboxed interpreter would be overkill for "compute
an annual cost from a monthly price." This is the right amount of power for
the task, not the maximum available power.

### Why Pydantic schemas (`src/schemas.py`) at every LLM boundary?
Every model output is untrusted until validated — `AgentAction`, `Comparison`,
`PriceFinding`, `EntailmentReport` all get parsed through a Pydantic model
before they're allowed to drive control flow. A malformed generation (bad
JSON, wrong enum value, missing field) degrades to a safe default (e.g.
`AgentAction(action="finish")`) instead of raising and crashing the graph.
This is the main reason the agent doesn't crash on a bad generation — it's
schema validation, not prompt quality.

### Why this domain (software capability comparison) instead of the example (population growth)?
It naturally forces every required behavior at once: parsing an ambiguous
request, multi-step research across two products, per-criterion evidence
extraction, comparison, citation, and — importantly — a built-in reason to
need the three-state vocabulary, since "capability not mentioned" is common
and genuinely different from "capability confirmed absent."

---

## 2. Control flow, where it gets stuck, where it fails silently

**Walkthrough** (`src/graph.py`):
`validate` → (`clarify` → END) or → `plan` ⇄ `act` (gather loop) → `compare` →
`price` → `draft` → `verify` ⇄ `revise` (fix loop) → `finalize` → END.

**Where it could loop or stall, and what stops it:**
- **Gather loop:** capped by `MAX_STEPS=10` *and* `STALL_LIMIT=2` consecutive
  no-new-evidence steps (`config.py`). A no-progress step is a duplicate
  action (exact string match on `f"{action}:{input}"`) or a search/fetch that
  returns nothing. Both increment `stall`; two in a row forces `finish`. This
  is a real, tested bound — `RECURSION_LIMIT=90` in LangGraph is the outer
  safety net that should never actually fire.
- **Verify/revise loop:** capped by `MAX_REVISIONS=2`, but in practice it
  converges in exactly one pass — `revise` downgrades every cell that failed
  a gate, so on the next `verify` those cells are no longer `POLARIZED` and
  can't be flagged again. The cap is a safety margin, not a load-bearing
  limit.
- **What it does *not* protect against:** the planner can legitimately call
  `finish` before every `(product, criterion)` pair has had a *targeted*
  search. That's not a stuck loop — it's a silent coverage gap. The agent
  terminates cleanly and reports a truthful `unverified`, but the user gets a
  thinner answer than they might expect. This is the actual root cause of the
  two factual case failures (see §3), and it's the highest-value fix I'd make
  next: a coverage matrix that blocks `finish` until each pair has at least
  one attempt.
- **A real gap, not yet handled:** `llm_client.chat` raises `RuntimeError`
  after exhausting its own retry loop (network/Ollama-down failures). Nothing
  in `nodes.py` catches that — it propagates out of `run_agent` as an
  unhandled exception. Tool failures (search, fetch) are handled as data;
  *model-availability* failures are not. That's an honest gap I'd name if
  asked "where could it fail silently" — it actually fails loudly (crash),
  which is arguably the safer default, but there's no graceful degradation
  path today.

---

## 3. How do I know it works? How would I evaluate at scale?

Two tracks, 8 cases (`evals/cases.json`), scored by `evals/run_evals.py`:
- **Factual cases** score against a dated, hand-labeled `gold_key.json`:
  capability accuracy, hallucination rate, retrieval recall, grounding rate.
- **Behavioral cases** assert specific properties: clarification-only (no
  research) for an underspecified request, bounded termination under
  repeated junk search results, recovery from an injected fetch timeout,
  and correct handling of a genuinely undocumented capability.
- Unknown assertions **fail closed** rather than being silently skipped.
- Deterministic layer underneath: 12 pytest unit tests + `verify_cases.py`
  (mocked LLM, no network/Ollama) so the agent's control flow, gates, and
  recovery paths can be checked in CI without live-web flakiness.

**Last live run: 4/8 passed.** Grounding rate was 100% and hallucination
rate 0% on every scored factual case in both this run and the prior one —
the failures are all under-coverage (retrieval didn't find enough) or
over-extraction (pricing pulled multiple plans instead of the one
qualifying plan), never a fabricated claim slipping through. That
distinction — *safe misses vs. unsafe assertions* — is the core signal I'd
point to for "how do I know it works": the thing it's designed to prevent
(confident hallucination) is measured at zero across runs; the thing it
isn't yet good at (complete retrieval) is honestly visible in the metrics,
not papered over.

**At scale**, eyeballing 8 cases isn't enough. I'd want: (a) a much larger,
versioned gold set with periodic re-verification against live sources since
pricing/docs pages change; (b) the same assertion framework run nightly
against a fixed model version to catch silent regressions from an Ollama/
model update; (c) sampling live production traffic for human spot-review of
grounding-gate decisions, since the reviewer model itself is an imperfect
judge (see §4); (d) tracking retrieval recall as a first-class SLO, since
that's the actual bottleneck, not model quality.

---

## 4. Where does it hallucinate or break? How would I harden it for production?

- **It doesn't currently fabricate polarized claims** in measured runs (0%
  hallucination rate, both gates enforced structurally). Its failure mode is
  *safe but incomplete*: too many `unverified` cells when retrieval doesn't
  cover both products evenly.
- **Where it's genuinely weak:**
  - **Source quality isn't gated.** A quote can pass both grounding gates
    while coming from a low-authority third-party site rather than the
    vendor's own docs (I saw this in a case-1 trace — a result from
    `agentsapis.com` got fetched alongside official ClickUp/Notion domains).
    Grounded ≠ authoritative. I'd add a deterministic official-domain
    allowlist/check as a third gate.
  - **Pricing plan selection** (case 5): the extractor pulls every price
    mentioned rather than deterministically selecting the lowest qualifying
    paid plan, so billing-context and plan-name assertions failed even
    though the correct totals appeared. This is an extraction-scope bug, not
    a grounding failure — the cited numbers were real.
  - **The reviewer is still an LLM.** Gate 1 (substring match) is fully
    deterministic and load-bearing; gate 2 (entailment) is a judgment call by
    a 4B model. It's a meaningfully independent check, not an infallible one.
  - **`fetch_url` takes a model-chosen URL with no allowlist.** In a
    production setting where the planner's `action_input` could be
    influenced by adversarial page content (prompt injection via a fetched
    page suggesting a next URL), an unrestricted fetch is a soft SSRF/
    exfiltration surface. I'd add a domain allowlist and block
    non-http(s)/internal-IP targets before hardening this for prod.
- **Hardening priorities in order:** (1) coverage matrix to fix under-
  retrieval, (2) official-domain gate, (3) URL allowlist on `fetch_url`,
  (4) graceful degradation instead of a raised exception on LLM-call
  exhaustion, (5) deterministic lowest-plan selection for pricing.

---

## 5. Scaling to 10,000 requests/day, reliably and cheaply

Current cost per comparison: ~9-14 LLM calls and 5-9 tool calls per case in
the latest run, ~135s wall-clock for the full 8-case suite's worth of work
spread across cases (individual comparisons ran 10-33s). At 10k/day that's
roughly 70-140k LLM calls/day on a single local Ollama instance doing
sequential, unbatched inference — that's the real bottleneck, not the graph
logic. Changes I'd make, roughly in priority order:
1. **Cache repeated research.** Popular comparisons (e.g. "Notion vs
   ClickUp") recur across users; a results/evidence cache keyed by normalized
   `(product, criterion)` would cut both search and LLM-comparison calls
   dramatically without touching correctness.
2. **Move off a single local Ollama process.** Either horizontally scale
   Ollama replicas behind a queue, or move to a hosted low-cost API with
   real concurrency/batching — a single sequential generator is a hard
   ceiling regardless of code-level optimization.
3. **Swap DuckDuckGo scraping for a rate-limited, paid search API** (e.g.
   Tavily/Serper/Bing). Unauthenticated scraping has no throughput contract
   and is the most likely thing to break first under real load — it already
   shows shallow/irrelevant snippets in eval traces at low volume.
4. **Move from synchronous CLI invocation to a queued worker model**
   (e.g. Celery/RQ or an async task queue) so requests don't block on a
   135-second graph run, with backpressure instead of unbounded concurrent
   Ollama calls.
5. **Tighten `MAX_STEPS`/model choice for the planner specifically** — the
   entailment call is already batched (one reviewer call per `verify` pass,
   not per cell), which is the right pattern; the generator's plan/act loop
   is the more expensive per-request line item and is the best target for a
   cheaper/faster model or a lower step cap traded against coverage.

---

## 6. What did I cut for time, and what would I build next?

Named explicitly in `README.md` / `design_note.md`, not discovered after the
fact:
- **Coverage matrix** keyed by `(product, criterion)` to block `finish`
  before each pair has a targeted attempt — the single highest-value next
  change, since it's the direct cause of both factual-accuracy failures.
- **Official-domain / source-ownership check** as a deterministic grounding
  gate — currently "grounded" doesn't imply "from an authoritative source."
- **Deterministic lowest-qualifying-plan selection** for pricing, instead of
  surfacing every extracted price.
- **Semantic duplicate-action detection** — today it's exact string match,
  so two differently-phrased searches for the same thing both run.
- **Multi-turn resume** — case 6 asks a clarifying question and ends; it
  doesn't resume the same graph state after the user answers.
- **Conflicting-source detection and a browser/Playwright fallback** for
  JS-rendered pages that `requests`/BeautifulSoup can't read — left as
  documented stretch work, not attempted.

I stopped there deliberately rather than going further, per the exercise's
own time-box guidance — the project already demonstrates the loop, recovery,
grounding, self-correction, ambiguity handling, live evaluation, and
observability end to end; the remaining items are depth, not missing
categories.
