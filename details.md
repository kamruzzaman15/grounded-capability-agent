# End-to-End Project Walkthrough

This document explains the complete project from the moment a user types a
request until the final answer is printed. It also explains the live evaluation
and deterministic offline tests, which are separate from a normal agent run.

## 1. The project in plain language

The application compares two software products using evidence found on the web.

Example request:

```text
Compare Notion and ClickUp on public API access and Slack integration
for a 15-person engineering team.
```

The agent must do more than ask a model for an answer. It must:

1. Understand which products and capabilities the user named.
2. Decide what information to search for.
3. Call search and page-fetch tools.
4. Observe whether those calls succeeded or failed.
5. Decide whether more research is needed.
6. Turn the collected evidence into structured comparison cells.
7. Check that every positive or negative claim is supported.
8. Downgrade unsupported claims to `unverified`.
9. Render a final answer from the audited structured data.
10. Return evidence, traces, and operational statistics.

This repeated decision-making is what makes it an agent rather than a single
prompt-to-model call.

## 2. Important terms

### LLM

LLM means large language model. This project uses:

- `qwen2.5:14b` as the generator and planner
- `gemma3:4b` as the grounding reviewer

### Node

A node is one step in the LangGraph workflow. Examples are `validate`, `plan`,
`act`, `compare`, and `verify`.

### Edge or route

An edge decides which node runs next. For example, validation routes an
underspecified request to `clarify` and a complete request to `plan`.

### State

State is the shared data object carried from node to node. It is the agent's
working memory for one run.

### Tool

A tool is ordinary code that lets the agent interact with something outside the
model. This project has web search, page fetch, and calculator tools.

### Evidence

Evidence is a search snippet or fetched page text saved with an ID such as `E1`
or `E2`.

### Cell

A cell is one product/criterion result. Two products and three criteria require
six cells.

### Deterministic

Deterministic means that the same input follows fixed code and produces the same
result. The calculator, quotation substring check, unsupported-cell downgrade,
and final renderer are deterministic.

LLM generation and live web search are not deterministic. Their output can vary
between runs.

## 3. Repository responsibilities

| File | Responsibility |
| --- | --- |
| `main.py` | Command-line entry point and printed output |
| `src/agent.py` | Initializes state, invokes the graph, and returns results |
| `src/graph.py` | Declares nodes and routes |
| `src/state.py` | Defines the shared state contract |
| `src/nodes.py` | Implements every graph node |
| `src/prompts.py` | Builds prompts for each model task |
| `src/schemas.py` | Validates model-produced JSON with Pydantic |
| `src/llm_client.py` | Calls Ollama and extracts JSON |
| `src/tools.py` | Search, fetch, and calculator implementations |
| `src/config.py` | Step, retry, revision, and stall limits |
| `evals/cases.json` | Eight evaluation inputs and expected assertions |
| `evals/gold_key.json` | Dated factual labels and expected prices |
| `evals/run_evals.py` | Live evaluation, failure injection, and reports |
| `tests/verify_cases.py` | Deterministic mocked end-to-end checks |
| `tests/test_recovery.py` | Offline retry and duplicate-action tests |
| `tests/test_eval_harness.py` | Offline injection and rendering tests |

## 4. The complete graph

```text
validate --underspecified--> clarify --> END
   |
  plan <-----------------+
   |  \                  |
   |   \--tool--> act ---+       gather loop
   |
(finish / cap / stall)
   |
compare --> price --> draft --> verify --unsupported--> revise
                                   |  ^                    |
                                   |  +------ verify <-----+
                                   |
                                finalize --> END
```

There are two loops:

1. The gather loop alternates between `plan` and `act`.
2. The grounding loop alternates between `verify` and `revise` when unsupported
   cells exist.

## 5. Before the graph starts

Suppose the command is:

```bash
.venv/bin/python main.py "Compare Notion and ClickUp on public API access and Slack integration for a 15-person team."
```

`main.py` joins the command-line arguments into one goal string and calls:

```python
result = run_agent(goal)
```

`run_agent` is in `src/agent.py`. It records the start time, creates the initial
state, invokes the compiled graph, and later packages the result.

The initial state looks conceptually like this:

```python
{
    "goal": "Compare Notion and ClickUp ...",
    "parsed": {},
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
    "final": {},
    "llm_calls": 0,
    "tool_calls": 0,
}
```

The graph is compiled once and cached in `_GRAPH`. Later calls reuse the same
compiled graph object.

## 6. How state accumulation works

Most state fields are replace-on-write. If a node returns a new `comparison`, it
replaces the previous comparison.

Four list fields use a LangGraph reducer:

```python
scratchpad: Annotated[List[str], operator.add]
trace: Annotated[List[str], operator.add]
evidence: Annotated[List[Dict[str, Any]], operator.add]
seen_actions: Annotated[List[str], operator.add]
```

`operator.add` means that a node returns only new entries, and LangGraph appends
them to the existing list.

Example:

```text
Existing trace:
  ["validate: ..."]

Plan node returns:
  ["plan#1: web_search(...)"]

New accumulated trace:
  ["validate: ...", "plan#1: web_search(...)"]
```

The state exists only for one graph run. It is not persistent conversational
memory. If the process ends, the state is lost unless the caller writes the
returned artifacts to a file.

## 7. Step 1: validate the request

The graph begins at `validate_node`.

For a normal CLI request, `parsed` is empty, so Qwen receives a parsing prompt.
The requested JSON shape is:

```json
{
  "products": ["Notion", "ClickUp"],
  "criteria": ["public API access", "Slack integration"],
  "team_size": 15,
  "wants_pricing": false
}
```

The response is processed by `extract_json` and validated by the `ParsedGoal`
Pydantic schema.

If parsing fails, the code falls back to an empty `ParsedGoal`. This safely
avoids executing malformed model output, although it can turn a valid request
into a clarification request.

The node adds a trace entry such as:

```text
validate: products=['Notion', 'ClickUp'] criteria=['public API access', 'Slack integration'] pricing=False
```

### Evaluation seeding

Live factual evaluation behaves slightly differently. The evaluator supplies
canonical products and criteria as a `seed`. When products already exist in
state, validation trusts the seed and does not call the parser model.

This keeps gold-key scoring stable, but it means the evaluation does not measure
free-text parsing accuracy.

## 8. Step 2: route to clarification or research

`route_after_validate` checks:

```python
if fewer_than_two_products or no_criteria:
    return "clarify"
return "plan"
```

### Clarification example

Input:

```text
Which is better, Notion or ClickUp?
```

There are two products but no criteria. The graph runs `clarify_node`, which
returns a deterministic question:

```text
I can compare Notion, ClickUp, but I need the criteria. Which capabilities
should I compare, for example API access, integrations, permissions, or
automation?
```

Then the graph ends. It does not search and does not call another model.

The current application cannot resume the same state after the user responds.
That is a documented multi-turn limitation.

## 9. Step 3: plan the next action

For a complete request, the graph enters `plan_node`.

The planning prompt includes:

- parsed products
- parsed criteria
- up to 180 characters from every evidence item
- the six most recent scratchpad entries
- the available action definitions

The model must return one JSON action:

```json
{
  "thought": "Find official Notion API documentation first.",
  "action": "web_search",
  "action_input": "Notion official public API documentation"
}
```

The `AgentAction` schema allows only:

- `web_search`
- `fetch_url`
- `finish`

The plan is saved as `next_action`, and a readable version is appended to the
scratchpad and trace. The `step` counter increases by one for each planning
decision.

### Important parse-failure behavior

If the planner output cannot be parsed or validated, the code creates this safe
fallback:

```python
AgentAction(
    action="finish",
    action_input="",
    thought="unparseable plan, finishing",
)
```

This avoids executing an invalid action, but it may finish research too early.
A stronger implementation would route parse failures into a visible re-prompt
or recovery state rather than treating them like an intentional finish.

## 10. Step 4: decide whether to act or compare

`route_after_plan` sends execution directly to `compare` when any of these is
true:

1. The planner selected `finish`.
2. `step` reached `MAX_STEPS`, currently 10.
3. `stall` reached `STALL_LIMIT`, currently 2.

Otherwise, it routes to `act`.

Notice that `MAX_STEPS` counts planning decisions, not every LangGraph node.

## 11. Step 5: execute an action

`act_node` reads `next_action` and calls the corresponding tool.

### Exact duplicate protection

The action signature is:

```python
signature = f"{action}:{action_input}"
```

If that exact signature already exists in `seen_actions`, the tool is not called.
The node adds a duplicate observation and increases `stall`.

This catches exact repeats but not semantically equivalent queries such as:

```text
Notion official API documentation
official docs for the Notion API
```

Those are different strings and therefore different signatures.

## 12. Web search behavior

`web_search` uses DuckDuckGo through the `ddgs` package and returns at most five
results. Each result contains:

```python
{
    "title": "...",
    "snippet": "...",
    "url": "...",
}
```

The action node converts every result into evidence:

```python
{
    "id": "E1",
    "source": "https://developers.notion.com/...",
    "title": "Notion API",
    "content": "Search-result snippet text...",
}
```

Evidence IDs are assigned in order using the current evidence length.

If search raises an exception or returns no results, the tool returns
`ok=False`. The failure becomes an observation for the next planner step.

### Current weakness

Any non-empty search result is counted as progress, even if it is irrelevant.
The system does not yet deterministically reject results that fail to mention
the product or criterion. This is why Case 8 needs an explicit step limit and
why a future relevance filter would be valuable.

## 13. Page-fetch behavior and retries

`fetch_url` uses Requests with:

- a 15-second timeout
- a browser-like user agent
- `raise_for_status()` for HTTP errors
- BeautifulSoup for text extraction

It removes scripts, styles, navigation, headers, footers, and sidebars. It then
normalizes whitespace and keeps the first 2,500 characters.

If the first fetch fails, `act_node` retries it up to `MAX_RETRIES`, currently 2.
Therefore, one action can make at most three HTTP attempts:

```text
initial attempt + retry 1 + retry 2
```

If retry 1 succeeds:

```text
attempt 1: timeout
attempt 2: success
retries counter: 1
tool_calls counter increase: 2
```

If every attempt fails, the scratchpad tells the planner to fall back to another
search or official URL.

The general `retries` statistic counts only these repeated fetch attempts. A new
search query is replanning, not a retry in the current metric.

## 14. The gather loop

After `act`, the graph returns to `plan`. The new planning prompt now contains
the evidence and recent observations.

A simplified run might look like:

```text
plan#1: web_search("Notion official API")
act: 5 search results added as E1-E5

plan#2: fetch_url("https://developers.notion.com/")
act: full page excerpt added as E6

plan#3: web_search("ClickUp official API")
act: 5 results added as E7-E11

plan#4: fetch_url("https://developer.clickup.com/")
act: page excerpt added as E12

plan#5: finish()
```

The gather loop is flexible, but coverage is not deterministic. The planner can
finish without researching every pair. For two products and three criteria, the
future improvement is a six-entry coverage matrix that prevents untouched pairs
from being skipped.

## 15. Step 6: build structured comparison cells

After the gather loop, `compare_node` sends the products, criteria, and up to 400
characters from every evidence item to Qwen.

The requested response shape is:

```json
{
  "cells": [
    {
      "product": "Notion",
      "criterion": "public_api_access",
      "label": "verified_present",
      "citation_id": "E6",
      "quote": "With the REST API, you can read, create, and update..."
    },
    {
      "product": "ClickUp",
      "criterion": "public_api_access",
      "label": "unverified",
      "citation_id": "",
      "quote": ""
    }
  ]
}
```

The `Comparison` and `Cell` Pydantic schemas validate the response.

If parsing fails completely, comparison begins with no cells. Code then adds a
safe `unverified` cell for every missing product/criterion pair. This ensures
that malformed model output does not silently omit requested cells.

The code fills missing pairs, but it does not currently remove unexpected extra
cells or normalize slightly different criterion names. That is another possible
hardening improvement.

## 16. Understanding the three labels

### `verified_present`

Meaning: the cited evidence explicitly establishes that the product has the
capability.

Required data:

```json
{
  "label": "verified_present",
  "citation_id": "E6",
  "quote": "exact evidence substring"
}
```

### `verified_unavailable`

Meaning: a source explicitly states that the capability is unavailable or not
supported.

It also requires a citation and exact quotation. The agent must not infer this
label merely because it found nothing.

### `unverified`

Meaning: the collected evidence did not establish either polarity.

It carries no citation or quote:

```json
{
  "label": "unverified",
  "citation_id": "",
  "quote": ""
}
```

`unverified` is not the same as “unavailable.” It is a statement about the
agent's evidence, not necessarily a statement about the product.

## 17. Step 7: optional pricing

`price_node` checks `wants_pricing`.

If pricing was not requested, it returns immediately without an LLM call:

```text
price: not requested, skipped
```

If pricing was requested, Qwen extracts candidate price findings:

```json
{
  "product": "Notion",
  "per_user_monthly": 10,
  "plan_name": "Plus",
  "citation_id": "E13",
  "quote": "$10 per user per month"
}
```

Code then checks:

1. A numeric price exists.
2. The textual form of that number appears in the quote.
3. The citation ID exists.
4. The quote is a substring of the cited evidence.
5. Team size exists.

Only then does it call the calculator with:

```text
price * team_size * 12
```

Example:

```text
10 * 20 * 12 = 2400
```

### Pricing limitation found by evaluation

The latest live run extracted four price findings instead of exactly one lowest
qualifying plan per product. It calculated them correctly, but did not satisfy
the selection requirement.

This shows the distinction between extraction, selection, and calculation:

- Extraction asks, “What prices are in the evidence?”
- Selection asks, “Which one satisfies the user's plan rules?”
- Calculation asks, “What is the annual total?”

Only the third step is currently fully deterministic.

The numeric substring check is also simple. It is not a full currency or billing
parser, so a future implementation should normalize currency, billing period,
plan eligibility, and price units explicitly.

## 18. Step 8: create an initial draft

`draft_node` sends the structured cells and cost lines to Qwen and asks for a
concise comparison.

Originally, this draft was printed directly. That caused a bug: verification
could later downgrade a cell while the old prose retained the rejected claim.

The final renderer now overwrites this draft after verification. Therefore, the
current draft call is an intermediate artifact and is not the final source of
truth. The verifier audits structured cells, not the prose itself.

This means the draft call is currently an optimization opportunity: it consumes
an LLM call even though final output is rendered deterministically. It could be
removed, or it could be repurposed into a real critique stage whose output is
explicitly evaluated.

## 19. Step 9: grounding Gate 1

`verify_node` selects only polarized cells:

```python
asserted = [
    cell for cell in cells
    if cell["label"] in {"verified_present", "verified_unavailable"}
]
```

An `unverified` cell makes no positive or negative factual assertion, so it does
not require grounding.

For each asserted cell, Gate 1 verifies:

1. The citation ID exists in evidence.
2. The quote is non-empty.
3. The normalized quote is a substring of the cited evidence content.

Normalization lowercases text and collapses whitespace.

### Gate 1 failure example

Evidence:

```text
E1: Linear is an issue tracker for software teams.
```

Proposed cell:

```json
{
  "product": "Linear",
  "criterion": "FedRAMP authorization",
  "label": "verified_unavailable",
  "citation_id": "E1",
  "quote": "Linear is not FedRAMP authorized."
}
```

The quote does not exist in E1, so Gate 1 rejects it without calling the reviewer
for that cell.

## 20. Step 10: grounding Gate 2

Cells that survive Gate 1 are sent together to `gemma3:4b`.

The reviewer sees:

- product
- criterion
- proposed label
- quote

It does not use outside knowledge. It must return `supported` or `insufficient`.

### Gate 2 failure example

Quote:

```text
Linear takes security seriously.
```

Claim:

```text
Linear / FedRAMP authorization: verified_present
```

The quote is real, so Gate 1 passes. However, it does not mention FedRAMP, so the
reviewer should return `insufficient` and Gate 2 rejects it.

### Current Gate 2 weakness

The code records explicit `insufficient` verdicts. If the reviewer omits a cell
entirely, that omitted cell is not automatically rejected. A stricter version
should initialize every survivor as unsupported and remove that failure only
after receiving an explicit matching `supported` verdict.

## 21. Step 11: revise unsupported cells

If the audit contains unsupported cells and revisions remain, routing sends the
graph to `revise_node`.

Revision is deterministic. It does not ask Qwen to try again.

Before:

```json
{
  "label": "verified_present",
  "citation_id": "E9",
  "quote": "weak or fabricated quote"
}
```

After:

```json
{
  "label": "unverified",
  "citation_id": "",
  "quote": ""
}
```

The `revisions` counter increases, and the graph returns to `verify`.

The second verification sees fewer asserted cells. Since rejected cells are now
unverified, the loop normally converges immediately. `MAX_REVISIONS`, currently
2, provides an additional bound.

## 22. Step 12: deterministic final rendering

When verification has no remaining unsupported cells, the graph runs
`finalize_node`.

It constructs the structured final object:

```python
{
    "type": "answer",
    "cells": final_cells,
    "cost": cost_data,
    "sources": all_evidence_sources,
    "unverified": list_of_unverified_pairs,
    "grounding_rate": ...,
}
```

It also renders the final answer directly from the audited cells.

Example:

```text
Capability comparison:

- Notion / public API access: verified_present [E6]
- ClickUp / public API access: unverified

Recommendation:
Based only on the verified capabilities above, Notion has the strongest
documented coverage. Confirm every unverified item that matters to your team
before deciding.
```

An unverified cell cannot receive a citation from this renderer. That fixes the
earlier stale-prose bug.

### Recommendation behavior

The renderer counts `verified_present` cells per product. If one product has
more, it names that product as having stronger documented coverage. If there is
a tie or no verified capability, it says the evidence does not establish a
unique winner.

This recommendation is safe but simplistic. It does not weight user priorities,
plan restrictions, feature quality, or pricing. A future version should produce
and audit a structured recommendation based on explicit priorities.

### Sources behavior

The final `sources` list includes every collected evidence source, not only
sources cited by surviving claims. Therefore, appearing in the source list does
not mean the source supports a final claim.

## 23. Grounding-rate calculation

The finalizer identifies all polarized cells and counts how many have a citation:

```text
grounding rate = polarized cells with citations / all polarized cells
```

If there are no polarized cells, grounding rate is defined as 100% because there
are no unsupported positive or negative claims.

Example:

```text
6 cells total
2 verified_present with citations
4 unverified

polarized cells = 2
polarized cells with citations = 2
grounding rate = 2 / 2 = 100%
```

This does not mean six of six facts were found. Retrieval recall may still be
only 33%. Grounding measures support for surviving assertions, not completeness.

## 24. What `run_agent` returns

After the graph ends, `run_agent` returns:

```python
{
    "goal": original_goal,
    "answer": final_rendered_text,
    "final": structured_final_object,
    "evidence": all_evidence,
    "prices": extracted_price_findings,
    "audit": final_audit,
    "trace": accumulated_trace,
    "stats": {
        "llm_calls": ...,
        "tool_calls": ...,
        "steps": ...,
        "retries": ...,
        "revisions": ...,
        "seconds": ...,
    },
}
```

`main.py` prints the answer, cells, cost, unverified pairs, sources, grounding
rate, statistics, and numbered trace.

The `tool_calls` metric currently counts search and fetch attempts in `act_node`.
Calculator usage is validated in pricing output but is not consistently included
in this general counter.

## 25. A complete normal-run example

Assume the user asks:

```text
Compare Product A and Product B on public API access.
```

### A. Validation

```json
{
  "products": ["Product A", "Product B"],
  "criteria": ["public API access"],
  "wants_pricing": false
}
```

Two products and one criterion means two required cells.

### B. Planning and action

```text
plan#1: search Product A official API
act: save snippets as E1-E5

plan#2: fetch Product A developer page
act: save page as E6

plan#3: search Product B official API
act: save snippets as E7-E11

plan#4: finish
```

### C. Comparison proposal

```json
{
  "cells": [
    {
      "product": "Product A",
      "criterion": "public API access",
      "label": "verified_present",
      "citation_id": "E6",
      "quote": "Build applications using the Product A public API."
    },
    {
      "product": "Product B",
      "criterion": "public API access",
      "label": "verified_present",
      "citation_id": "E9",
      "quote": "Product B is easy to use."
    }
  ]
}
```

### D. Gate 1

- Product A quote exists in E6: pass.
- Product B quote exists in E9: pass.

### E. Gate 2

- Product A quote directly states public API access: supported.
- Product B quote only says it is easy to use: insufficient.

### F. Revision

Product B becomes:

```json
{
  "label": "unverified",
  "citation_id": "",
  "quote": ""
}
```

### G. Final output

```text
- Product A / public API access: verified_present [E6]
- Product B / public API access: unverified
```

The system does not convert Product B to `verified_unavailable`, because no
evidence explicitly said the API was unavailable.

## 26. A complete failure-recovery example

Evaluation Case 4 contains this failure specification:

```json
{
  "tool": "extract_page",
  "url_pattern": "mural",
  "failure_mode": "timeout",
  "failures_before_success": 1
}
```

During evaluation only, `inject_case_failures` temporarily wraps
`nodes.fetch_url`.

When the agent first fetches a URL containing `mural`, the wrapper returns:

```python
{
    "ok": False,
    "error": "injected timeout",
    "url": requested_url,
}
```

The action node sees a normal tool failure and retries. On the second call, the
wrapper delegates to the real fetch tool.

Latest trace excerpt:

```text
plan#3: fetch_url(https://mural.co/)
act: fetch retry 1 for https://mural.co/
act: fetch https://mural.co/ -> ok (E7)
```

The evaluator then checks all declared recovery assertions:

- an injected failure event exists
- retry count is at least one
- another query or source was used
- no ungrounded polarized claim survived
- execution stayed within its step limit

This injection is not part of a normal user run. It is test-only code used to
prove that the real runtime recovery path works.

## 27. Normal pipeline versus evaluation versus offline tests

These are three different contexts.

| Context | Real models | Real web | Same graph | Purpose |
| --- | ---: | ---: | ---: | --- |
| Normal CLI run | Yes | Yes | Yes | Answer one user request |
| Live evaluation | Yes | Yes, except configured injections | Yes | Measure realistic behavior |
| Deterministic offline tests | No | No | Often yes | Verify logic repeatably |

## 28. Live evaluation process

Running:

```bash
.venv/bin/python evals/run_evals.py
```

does the following for every case in `evals/cases.json`:

1. Read case ID, track, products, criteria, assertions, and failure specification.
2. Seed canonical products and criteria into agent state.
3. Temporarily install the configured failure or junk-result wrapper.
4. Run the real graph with the configured Ollama models.
5. Restore the original tools.
6. Score factual metrics when a gold key exists.
7. Evaluate every assertion declared by the case.
8. Mark the case `PASS` only if every declared assertion passes.
9. Save the answer, evidence, prices, audit, injected events, trace, and stats.

An assertion name that the evaluator does not recognize fails closed. It is not
silently ignored.

## 29. Factual evaluation metrics

### Capability accuracy

```text
correct cell labels / total gold cells
```

If two of six cell labels match the gold key, accuracy is 33%.

### Hallucination rate

This counts a polarized output that contradicts the gold label.

Returning `unverified` for a gold `verified_present` cell hurts accuracy and
recall but is not counted as a polarized hallucination. That is a safe miss.

### Retrieval recall

For gold cells that are answerable with a polarized label, recall checks whether
the agent produced a citation.

### Grounding rate

This measures citations on final polarized claims, as explained earlier. It can
be 100% while accuracy and recall are low.

## 30. Behavioral evaluation

Behavioral cases test system properties rather than a complete factual key.

Examples:

- Case 3 requires undocumented security claims to remain unverified.
- Case 4 requires observable timeout recovery and safe output.
- Case 6 requires clarification without research.
- Case 8 requires safe bounded termination under repeated irrelevant results.

This explains why Case 4 can pass even when all final capabilities are
unverified. The case proves recovery behavior, not full factual resolution.

## 31. Deterministic offline tests

Offline tests are not an extra node in the agent pipeline. They are test programs
that call the same functions and graph while replacing nondeterministic
boundaries.

### What is replaced?

- Ollama responses become predefined JSON strings.
- Web search becomes a fixed mapping from query text to results.
- Fetch becomes a predefined success or failure.

### What remains real?

- graph routing
- state accumulation
- retry loop
- comparison completion
- deterministic quote gate
- revision logic
- pricing guard
- final rendering
- trace and counters

### Example scripted planner

```python
[
    {"action": "web_search", "action_input": "Notion API docs"},
    {"action": "web_search", "action_input": "ClickUp API docs"},
    {"action": "finish", "action_input": ""},
]
```

Because the model and web outputs are fixed, the same test follows the same path
every time. This is useful for CI and regression testing.

### Why both offline and live evaluation are needed

Offline tests answer:

```text
Does my retry or grounding code work under a known scenario?
```

Live evaluation answers:

```text
Do the current models and web tools behave usefully in realistic conditions?
```

Offline success cannot guarantee live retrieval quality. Live success alone can
be accidental and difficult to reproduce. The two methods complement each
other.

## 32. Evaluation output files

### `evals/results.md`

This is the readable report. It includes:

- generator and reviewer names
- per-case PASS or FAIL
- factual metrics or pricing results
- runtime statistics
- every assertion result
- injected-event count
- per-node trace

### `evals/run_artifacts.json`

This is the detailed machine-readable artifact. It includes:

- model metadata and timestamp
- case input and outcome
- assertion dictionary
- factual and pricing metrics
- injected failure events
- final answer and structured cells
- all evidence
- price findings
- audit
- trace
- operational statistics

The file currently stores only the latest run because the next evaluation
overwrites it. Production or serious experimentation should use timestamped or
run-ID-based artifact paths.

## 33. Why the latest hardened run passed only 5 of 8 cases

### Case 1 failure

The planner researched Notion more heavily than ClickUp and failed to cover all
six gold cells. The final output was safely grounded but incomplete.

### Case 5 failure

The agent found the expected $2,400 and $1,680 totals, but also extracted extra
plans and omitted required plan/billing metadata. The stricter assertions
correctly failed the case even though a naive substring price metric found both
expected numbers.

### Case 7 failure

The planner focused on Figma and under-researched Canva, again showing that the
main weakness is deterministic coverage rather than arithmetic or graph routing.

## 34. Main current limitations

1. The planner may finish before every product/criterion pair is attempted.
2. Search results are not deterministically filtered for relevance.
3. Official-domain and product-source ownership are not hard grounding gates.
4. Page extraction is limited to the first 2,500 characters.
5. JavaScript-heavy or anti-bot pages can fail.
6. Gate 2 does not yet fail closed when a reviewer verdict is omitted.
7. The intermediate draft LLM call is currently overwritten by final rendering.
8. Recommendation logic counts verified features instead of modeling priorities.
9. Pricing selection is model-driven and can return extra plans.
10. Evaluation seeds parsing fields, so free-text parsing is under-tested.
11. The general tool-call count does not fully represent calculator usage.
12. Live failure injection patches module-level functions and is unsuitable for
    concurrent evaluation processes.
13. Multi-turn resume and durable graph checkpoints are not implemented.
14. Live web and model results can change between runs.

## 35. Highest-value improvements

### Improvement 1: coverage matrix

Create one record per requested pair:

```python
{
    ("Notion", "public_api_access"): "evidenced",
    ("Notion", "slack_integration"): "searched",
    ("ClickUp", "public_api_access"): "not_attempted",
    ("ClickUp", "slack_integration"): "not_attempted",
}
```

Do not allow `finish` while a pair is `not_attempted`, unless the global safety
cap has been reached.

### Improvement 2: source-policy gate

Maintain official-domain mappings and verify that cited evidence belongs to the
claimed product. Treat third-party sources as discovery hints rather than final
claim evidence when official sources are required.

### Improvement 3: deterministic pricing selection

Extract candidates into a normalized schema, then filter and choose the lowest
qualifying plan in code. Calculate only the selected plan.

### Improvement 4: fail-closed reviewer

Require exactly one explicit supported verdict for every asserted cell. Missing,
duplicate, or malformed verdicts should cause downgrade.

### Improvement 5: structured model responses

Use model-supported JSON schemas and route parse failure into retry/replan rather
than `finish`.

## 36. What is part of the runtime pipeline?

Runtime components:

- parsing
- clarification route
- planner
- search and fetch tools
- fetch retry loop
- state, evidence, and trace accumulation
- comparison and pricing
- both grounding gates
- deterministic downgrade
- deterministic final renderer
- returned statistics

Not runtime components:

- mocked model responses in tests
- test-only failure injection
- gold-key scoring
- evaluation assertions
- `results.md` generation
- `run_artifacts.json` generation

The normal caller receives artifacts from `run_agent`; the evaluation harness is
responsible for writing them to disk.

## 37. Final mental model

The easiest way to remember the whole system is:

```text
Understand
  Parse the user's goal or ask for clarification.

Research
  Let the planner choose one search/fetch action at a time.
  Store observations and evidence in state.
  Retry bounded fetch failures.

Structure
  Produce one cell for every product and criterion.
  Extract and calculate prices only from cited numbers.

Audit
  Check that the quote exists.
  Ask a separate model whether it supports the claim.
  Downgrade failures to unverified.

Render
  Build the answer from audited cells.
  Return cells, sources, evidence, trace, and statistics.

Evaluate separately
  Use fixed mocks for repeatable logic tests.
  Use live models/web for realistic evaluation.
  Inject failures to prove recovery.
  Score every declared assertion and save artifacts.
```

The project's strongest property is that unsupported claims can be changed by
deterministic code rather than relying only on another prompt. Its main weakness
is that the planner can still fail to collect complete, balanced evidence before
that grounding process begins.
