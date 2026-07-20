# Interview Q&A V2 — Grounded Capability Comparison Agent

This document is an interview-preparation guide for the project. The answers are
written to be honest about what is implemented, what the evaluation actually
proves, and where the system can still fail.

## 60-second project explanation

I built a LangGraph research agent that compares two software products across
user-specified capabilities. It parses the request, repeatedly plans and invokes
web tools, accumulates evidence in typed state, produces one structured cell per
product and criterion, and audits every positive or negative claim before
returning it.

The key design rule is that missing evidence is not evidence that a feature is
unavailable. Each cell is therefore one of `verified_present`,
`verified_unavailable`, or `unverified`. A polarized claim survives only when its
quote exists in the cited evidence and a separate reviewer model judges that the
quote entails the claim. Rejected cells are deterministically downgraded to
`unverified`. The final prose is rendered from those audited cells so stale or
rejected citations cannot remain in the answer.

The project includes eight live evaluation cases, deterministic offline tests,
injected tool failures, assertion-level reporting, operational counters, and
complete per-node traces.

## Current configuration and evidence

- Generator/planner: `qwen2.5:14b`
- Grounding reviewer: `gemma3:4b`
- Framework: LangGraph
- Tools: DuckDuckGo search, HTTP/BeautifulSoup fetch, safe AST calculator
- Latest hardened live result: 5/8 cases passed
- Latest live runtime: 135.9 seconds
- Latest live operations: 72 LLM calls, 45 tool calls, 51 planning steps,
  7 retries, and 3 grounding revisions
- Offline checks: 12/12 unit tests and 10/10 mocked evaluation checks passed

The three failed live cases are important evidence, not something to hide:

- Case 1 under-researched the Notion/ClickUp capability matrix and reached only
  33% factual accuracy.
- Case 5 found the two expected annual totals but extracted extra plans and
  failed plan-name, annual-billing, and lowest-plan-selection assertions.
- Case 7 focused too heavily on Figma and under-researched Canva, reaching 33%
  factual accuracy.

## Architecture walkthrough

```text
validate --underspecified--> clarify --> END
   |
  plan <-----------------+
   |  \                  |
   |   \--tool--> act ---+       bounded gather loop
   |
(finish / cap / stall)
   |
compare --> price --> draft --> verify --unsupported--> revise
                                   |  ^                    |
                                   |  +------ verify <-----+
                                   |
                              final_render --> END
```

The state carries the parsed goal, evidence, scratchpad observations, attempted
actions, comparison cells, price findings, audit, per-node trace, and counters.
List-valued fields such as evidence and trace use LangGraph reducers so nodes
append deltas instead of replacing history.

## Why did you choose LangGraph?

I chose LangGraph because the control flow has two real loops and multiple
conditional exits. It makes the gather loop, clarification branch, retry limits,
and verify/revise loop explicit. Typed state also gives every node one shared
contract, and the accumulated trace makes a run auditable.

A plain Python loop would be a valid and lighter alternative at this project
size. I would choose it if dependency minimization were the primary concern.
LangGraph earns its cost here mainly through visible routing, testable state
transitions, and a clear path to checkpointing or human approval later.

I would not claim that LangGraph automatically makes the agent reliable. The
reliability comes from explicit caps, validated state, deterministic guards, and
tests. LangGraph only provides a useful structure for those decisions.

## Why use an agent loop instead of one large prompt?

The task needs information that is not known at prompt time. A single call
cannot reliably search, react to a failed page, try another source, calculate a
price, and decide whether evidence is sufficient. The plan/act/observe loop lets
the model choose another action after seeing actual tool output.

The cost is nondeterminism and more latency. I bound that cost with a maximum
step count, duplicate-action detection, a stall counter, and retry limits.

## Why separate planning and acting?

The planner decides what should happen next; the action node owns tool execution
and failure contracts. This separation means tool errors are returned as data
rather than becoming unhandled model exceptions. It also lets tests mock tools
without changing planning logic.

The weakness is that the planner still has too much freedom. It can choose
`finish` before researching every product/criterion pair. That caused Cases 1
and 7 to under-retrieve. My next improvement would make coverage partly
deterministic instead of leaving it entirely to the planner.

## Why three labels instead of yes/no?

A binary label forces the agent to confuse “I found no evidence” with “the
vendor explicitly says this is unavailable.” Those are different claims.

- `verified_present` requires supporting evidence that the capability exists.
- `verified_unavailable` requires explicit evidence that it is not available.
- `unverified` means the checked evidence established neither conclusion.

This vocabulary intentionally favors safe misses. It may reduce recall, but it
prevents silence from becoming a fabricated negative claim.

## Why two models?

The generator plans research and proposes comparison cells. The reviewer has a
narrower job: decide whether each quotation entails the proposed label. Using a
different model family reduces correlated errors compared with asking the same
model to approve its own work.

This is not perfect independence. Both models were trained on overlapping public
data, and the reviewer can still make mistakes. That is why the first gate is a
deterministic substring check and remains the load-bearing protection against
fabricated quotations.

## Why Qwen 2.5 14B and Gemma 3 4B?

I tested several local generators. Qwen 2.5 14B gave the best observed balance
of JSON reliability, latency, and factual behavior. Qwen 32B was much slower and
did not produce a proportional quality improvement. Gemma 27B performed
reasonably but would put the generator and reviewer in the same model family.

Gemma 3 4B is sufficient for the narrow entailment task and keeps review cheaper
than using another large generator. I selected models based on task behavior,
not headline benchmark rank.

The comparison was not perfectly controlled because live web results change
between runs and not every model was evaluated after every workflow revision. A
more rigorous model bake-off would freeze retrieved evidence, run repeated
seeds, and compare models on the same inputs and artifacts.

## Why validate LLM output with Pydantic?

LLM text is not a control-flow contract. Parsed goals, actions, comparison cells,
prices, and reviewer verdicts are validated through typed schemas before they
drive the graph. Malformed data degrades to safe defaults rather than directly
executing an arbitrary action.

One current limitation is that JSON extraction is best-effort. An unparseable
planner response becomes `finish`, which can stop research prematurely. A better
implementation would use Ollama's structured-output or JSON-schema support and
distinguish parse failure from an intentional `finish` action.

## Why these three tools?

### Web search

Search discovers candidate documentation without requiring a paid API key. It
can fail by returning no results or irrelevant results, which provides a real
recovery scenario.

Its weaknesses are unstable ranking, irrelevant snippets, and weak control over
official sources.

### Page fetch

Fetching lets the agent retrieve more evidence than a short search snippet. It
uses Requests and BeautifulSoup because that is simple and inspectable.

It can fail on timeouts, 403 responses, JavaScript-rendered pages, redirects, or
because the relevant text occurs after the 2,500-character extraction limit.

### Calculator

The calculator separates arithmetic from language generation. It parses only
numeric AST operations and rejects calls, names, or attributes, avoiding `eval`
and arbitrary code execution.

The arithmetic is reliable, but price selection is not. The latest pricing case
proved that the model can correctly calculate several plans while still failing
the user's instruction to select the lowest qualifying plan.

## How does retry and recovery work?

`fetch_url` returns `{ok: false, error: ...}` instead of raising through the
graph. The action node retries the same failed fetch up to `MAX_RETRIES`. If all
attempts fail, the observation tells the planner to try another search or source.

The live evaluator now injects an actual Mural timeout for Case 4. The latest run
recorded the injected failure, retried once, recovered, and passed all five
recovery assertions. Case 8 injects repeated irrelevant search results and
checks that execution remains bounded and both fictional products remain
unverified.

The `retries` counter currently counts only failed page-fetch retries. It does
not count changed search queries, rejected junk results, or general replanning.
A production metric should separate fetch retries, search fallbacks, parse
failures, duplicate actions, and semantic no-progress events.

## Where could the agent get stuck?

The gather loop could repeat similar searches or fetches indefinitely if it had
no bounds. The current implementation limits this through:

- `MAX_STEPS`
- exact duplicate-action skipping
- a consecutive no-progress stall limit
- bounded fetch retries
- LangGraph's recursion limit as a final safety net

It can still waste steps on semantically equivalent queries because duplicate
detection uses exact action strings. A better guard would canonicalize URLs,
deduplicate evidence sources, and compare query similarity.

## Where could it fail silently?

The most important silent-failure risks are:

1. **Premature finish.** A valid JSON action can intentionally finish with
   product/criterion pairs still untouched.
2. **Planner parse failure.** An invalid action currently degrades to `finish`,
   which looks like a normal stop.
3. **Reviewer omission.** The current verifier handles explicit
   `insufficient` verdicts, but a reviewer that omits an asserted cell may not be
   treated as a rejection. I would change this to fail closed: every asserted
   cell must receive an explicit `supported` verdict.
4. **Wrong source ownership.** A quote may exist and sound relevant without
   coming from the claimed product's official domain.
5. **Truncated page content.** Relevant text beyond the extraction limit is
   invisible to the comparison model.
6. **Metric ambiguity.** A 100% grounding rate can coexist with poor factual
   accuracy because grounding measures support for surviving claims, not
   retrieval completeness.

The trace and artifacts reduce silent failure by making these paths observable,
but observability does not itself correct them.

## How does the grounding guard work?

Gate 1 checks that the normalized quotation is literally present in the cited
evidence. This catches fabricated quotes and incorrect evidence IDs.

Gate 2 sends the quote, product, criterion, and proposed label to the reviewer.
An explicit insufficient verdict causes a deterministic downgrade.

The revision node changes rejected cells to `unverified` and clears their quote
and citation. The final renderer then builds prose from those revised cells.

The deterministic final renderer was added because live tests exposed a real
bug: the structured cell was downgraded, but the earlier LLM prose still claimed
the rejected capability. Rendering from audited state makes the structured
cells and prose consistent.

## What does grounding rate actually prove?

It proves that final polarized cells retained citations after the grounding
process. It does not prove:

- that every requested fact was found
- that the source was official
- that the source belongs to the claimed product
- that a dated gold key is still current
- that the reviewer made the right semantic judgment
- that the final recommendation follows the user's priorities

This distinction explains why the project can report 100% grounding and only
33% capability accuracy in the same case.

## Why render the final answer deterministically?

Structured cells are the audited source of truth. Asking the model to rewrite
them after verification would reintroduce a chance of changing labels or adding
citations. The deterministic renderer ensures that only final cell labels and
citations appear in user-visible prose.

The tradeoff is less natural and less nuanced writing. The current
recommendation is also simplistic: it compares the number of verified-present
cells rather than fully modeling user priorities, pricing, or feature
importance. A better renderer would accept a structured recommendation object
that is separately audited against explicit priorities.

## How is state handled across steps?

The typed `AgentState` carries all information through one graph execution.
Evidence, scratchpad observations, attempted actions, and trace entries
accumulate through reducers. Scalars such as step count, retry count, comparison,
audit, and draft are replaced by the latest node output.

This is state within a run, not durable conversational memory. Case 6 asks a
clarifying question and ends. Resuming the same graph after the user answers is
not implemented. In production I would add a thread ID, checkpoint storage, and
a resume path that merges clarified criteria into existing state.

## Why keep a per-node trace?

Aggregate metrics tell me that a case failed; the trace explains how. It shows
queries, fetches, retries, duplicate actions, comparison size, audit rejections,
revisions, and finalization.

The CLI prints the trace. The live evaluator stores it in both
`evals/results.md` and `evals/run_artifacts.json` with evidence and assertion
results. This made it possible to diagnose premature stopping, retries, and
uneven product coverage.

The trace is currently human-readable text rather than structured telemetry. At
scale I would emit typed events with timestamps, node names, duration, outcome,
and correlation IDs to OpenTelemetry or another observability backend.

## How do you know the agent works?

I use complementary test layers:

1. Unit tests check safe calculation, retries, failure recovery, duplicate
   actions, final rendering, and evaluation injection.
2. Mocked graph tests exercise all eight cases deterministically without Ollama
   or network access, including both grounding gates and pricing guards.
3. Live evaluation runs the current models and web tools against factual and
   behavioral cases.
4. Factual cases compare labels against a dated gold key.
5. Behavioral cases enforce every declared assertion and fail closed for an
   unknown assertion.
6. Full artifacts preserve evidence, cells, prices, audits, injected failures,
   traces, and operational statistics.

This demonstrates behavior under tested conditions; it does not prove general
reliability across arbitrary products or changing documentation.

## Why seed products and criteria in live evaluation?

The live evaluator seeds canonical products and criteria so generated cell keys
match the gold key exactly. This reduces scoring noise and isolates research and
grounding behavior.

The consequence is that the free-text parse node is not covered by factual
scoring. Normal CLI runs still exercise it, but a stronger evaluation would add
dedicated parse cases for aliases, URLs, ambiguous product names, missing team
size, and pricing intent.

## What did the latest evaluation teach you?

The latest run showed that the control and safety paths are stronger than the
retrieval path:

- Failure injection and retry worked.
- Clarification worked without unnecessary research.
- Unsupported claims were revised and the final answer stayed consistent.
- Repeated junk results terminated safely.
- Asana/Trello achieved 100% factual accuracy in that run.
- Notion/ClickUp and Figma/Canva under-retrieved one side of the comparison.
- Pricing arithmetic was correct, but plan selection and metadata were not.

The main lesson is that using a larger model is not the next best investment.
The next improvements should constrain coverage, source policy, and pricing
selection deterministically.

## Why did Case 4 pass when its final capabilities were unverified?

Case 4 is a behavioral recovery test, not a factual completeness test. Its job
is to prove that a configured failure is detected, recovery is attempted, no
unsupported claim survives, and the run terminates within limits. Returning
`unverified` after recovery is acceptable when the recovered evidence is still
insufficient.

If I wanted Case 4 to test both recovery and factual resolution, I would add a
gold key and require at least one expected capability to resolve from the
post-recovery source.

## What went wrong in the pricing case?

The model found evidence containing the expected $10 Notion and $7 ClickUp
prices, and the calculator produced $2,400 and $1,680 for 20 users. But it also
extracted additional plans, omitted ClickUp plan names, and did not consistently
identify annual billing context. A naive metric saw both expected totals, while
the assertion-level evaluator correctly failed the case.

I would fix this by separating price extraction from plan selection:

1. Extract all candidate plans into a normalized schema.
2. Deterministically filter currency, annual billing, collaborative eligibility,
   and non-enterprise plans.
3. Select the minimum qualifying per-user price in code.
4. Calculate exactly one result per product.
5. Require the plan name, price quote, and billing-context quote before success.

## What would you improve first?

### Priority 1: deterministic coverage matrix

Track every `(product, criterion)` pair as `not_attempted`, `searched`,
`evidenced`, or `unresolved`. Do not allow `finish` while any pair is
`not_attempted`, unless the global cap is reached.

This directly targets the failures in Cases 1 and 7.

### Priority 2: source-policy gate

Map product names to official domains and reject polarized claims from
unapproved sources when a case requires official documentation. Validate that
the cited source belongs to the claimed product.

### Priority 3: deterministic pricing selection

Normalize candidate plans and select the lowest qualifying plan in code rather
than asking the model to perform selection and arithmetic together.

### Priority 4: fail-closed reviewer coverage

Require an explicit reviewer verdict for every asserted cell. Missing or
malformed verdicts should downgrade the claim.

### Priority 5: structured model output

Use schema-constrained Ollama responses and represent parse failure as an
observable error/replan state rather than an implicit finish.

## What would you not prioritize next?

I would not start with a larger model, multi-agent orchestration, or a polished
UI. The evaluation shows that deterministic workflow constraints would address
the failures more directly and cheaply. A multi-agent system could add cost and
failure modes without fixing incomplete coverage or weak source policy.

## What did you cut for time?

- multi-turn resume after clarification
- deterministic coverage tracking
- official-domain and product-source validation
- deterministic plan selection for pricing
- semantic duplicate-query and duplicate-URL detection
- JavaScript/browser fallback
- conflicting-source detection
- persistent run history rather than overwriting the latest artifact
- token-level cost accounting
- production API, queue, authentication, and UI

These are documented rather than partially hidden behind prompts.

## What would fail in production today?

- Dynamic or anti-bot documentation pages could block `fetch_url`.
- Search rankings could return irrelevant, stale, or adversarial content.
- Prompt injection inside fetched pages is not explicitly filtered.
- The planner could spend the full step budget without covering every pair.
- A source could change after the gold key was labeled.
- The reviewer could omit a verdict or approve a weak quotation.
- Concurrent live evaluations would be unsafe because failure injection patches
  process-global tool functions.
- The in-memory graph has no durable job state or cross-process resume.
- The latest report files are overwritten by the next run.
- The calculator is safe, but upstream price extraction can select the wrong
  plan or billing interval.
- Statistics count fetch/search attempts, but calculator use is not represented
  consistently in the general `tool_calls` metric.

## How would you handle prompt injection from web pages?

I would treat fetched content as untrusted data, never instructions. Concretely:

- delimit evidence clearly in prompts
- state that evidence cannot change system rules or select tools
- strip scripts, hidden content, and suspicious instruction-like blocks
- restrict fetches to approved domains for high-stakes comparisons
- keep tool selection in validated structured actions
- prevent evidence from supplying arbitrary URLs without policy checks
- log and flag suspicious content

The current BeautifulSoup cleanup removes scripts and navigation, but that is
not a complete prompt-injection defense.

## How would you scale this to 10,000 requests per day?

I would separate request orchestration from model workers:

1. Put requests on a durable queue with idempotency keys.
2. Persist graph checkpoints and artifacts in a database/object store.
3. Run stateless planner, fetch, reviewer, and rendering workers.
4. Cache search results and fetched official pages by normalized URL and content
   hash with freshness policies.
5. Deduplicate concurrent fetches to the same documentation URL.
6. Apply per-domain rate limits, exponential backoff, and circuit breakers.
7. Use a smaller model for parsing and simple planning, escalating only hard
   comparisons to the 14B generator.
8. Batch reviewer entailment checks and reuse evidence embeddings where useful.
9. Emit structured telemetry for latency, tokens, cost, tool success, retries,
   unsupported-claim rate, and coverage.
10. Add tenant isolation, authentication, quotas, secret management, and data
    retention controls.

I would also replace open web search with a controlled retrieval layer for
official documentation when reliability matters. At that scale, predictable
retrieval and caching will save more cost than simply choosing a smaller model.

## How would you reduce latency and cost?

- Require one targeted search per pair, then stop redundant planner iterations.
- Cache official pages and search results.
- Use direct known documentation URLs when available.
- Run parsing and routing on a smaller model.
- Batch all surviving cells into one reviewer request, as the current verifier
  already does.
- Avoid another LLM call for final prose; the current deterministic renderer
  already implements this optimization.
- Reject irrelevant sources before sending them into comparison prompts.
- Track tokens in addition to calls and seconds so optimizations are measurable.

The model-call count alone is only a rough cost proxy because calls have
different prompt and output sizes.

## How would you evaluate at larger scale?

I would build a versioned benchmark with:

- frozen evidence snapshots for reproducible model comparisons
- a separate live-web track for retrieval drift
- product/category diversity
- adversarial snippets and prompt-injection pages
- explicit source-policy labels
- expected tool trajectories for recovery cases
- repeated runs to estimate variance
- human-reviewed entailment labels
- metrics by stage: parse accuracy, coverage, source precision, retrieval recall,
  cell accuracy, unsupported-claim rate, reviewer false accept/reject rate,
  latency, tokens, and cost

I would also prevent train/test leakage by holding out products and criteria from
prompt development.

## Why not call the current evaluation production-grade?

The factual key is small, dated, and partly weak. Live search is nondeterministic.
Some behavioral assertions validate safe outcomes without validating factual
resolution. The evaluator now enforces declared assertions, but it is still only
eight cases and the source policy is not yet a deterministic gate.

It is a meaningful take-home evaluation harness, not a statistical guarantee of
production reliability.

## What is the most interesting bug you found?

The most useful bug was the stale-draft inconsistency. The verifier correctly
downgraded an unsupported cell, but the prose had already been generated and
still claimed that capability with a citation. The structured answer was safe;
the user-visible answer was not.

The fix was architectural rather than another prompt: render final prose from
the post-verification cells. That made the verified structured state the single
source of truth.

## What engineering choice are you most confident in?

The deterministic downgrade is the strongest choice. It gives the grounding
guard “teeth”: once a claim fails a gate, code—not another model instruction—
changes it to `unverified`. This guarantees convergence of the revision loop and
prevents an unsupported polarized cell from surviving merely because the model
refuses to revise itself.

## What choice would you reconsider?

I would reconsider giving the planner sole authority to decide when research is
complete. It made the graph flexible but produced asymmetric retrieval. A hybrid
design would generate deterministic coverage tasks first, then let the model
choose the best action within each task.

I would also make the evaluator and runtime share more validation code. For
example, official-source and product-ownership checks should be runtime gates,
not only evaluation expectations.

## How should you explain the 5/8 result?

I would say:

> The hardened evaluator passes five cases and intentionally fails three. The
> failures are concentrated in retrieval completeness and price-plan selection,
> not uncontrolled hallucination. The safety behavior is stronger than factual
> recall: all scored factual cases ended with zero gold-key contradictions, but
> two capability cases retrieved only one-third of the expected facts. I would
> address that with deterministic coverage and source-policy checks before using
> a larger model.

This answer is more credible than presenting 100% grounding as 100% correctness.

## Questions to ask the interviewer

If there is time, useful questions include:

- Is the intended production domain open-web research or a controlled document
  collection?
- Would you optimize first for recall, precision, latency, or cost?
- How strict should official-source policy be when vendor documentation is
  incomplete?
- Should `unverified` trigger a human review workflow or simply return to the
  user?
- What level of reproducibility do you expect from live-web evaluations?
- Would durable multi-turn clarification be more valuable than broader tool
  coverage for the target product?

## Five-minute walkthrough outline

1. State the three-label safety rule and why binary yes/no is unsafe.
2. Draw the gather loop and verify/revise loop.
3. Show `AgentState` and one accumulated trace.
4. Show the injected Case 4 timeout and retry.
5. Show a rejected cell being downgraded and the final renderer removing its
   citation.
6. Show the assertion-level evaluation report.
7. Be explicit about the three failed cases.
8. End with the coverage matrix as the next highest-value improvement.

## Claims I should avoid in the interview

Do not claim that:

- 100% grounding means 100% factual correctness
- every source is official
- the reviewer is infallible
- all model comparisons were perfectly controlled
- Case 4 proves the capabilities exist; it proves recovery and safe behavior
- pricing is solved because the expected totals appeared
- the agent supports durable multi-turn conversations
- exact duplicate detection catches semantic duplicates
- the application is ready for 10,000 daily production requests

The strongest interview posture is to explain exactly what each mechanism
guarantees, show evidence for that guarantee, and name the next failure boundary.
