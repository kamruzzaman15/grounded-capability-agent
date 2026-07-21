# Grounded Product Capability Comparison Agent

An agentic research assistant that compares two software products using public
web evidence. Given a natural-language goal, it parses the request, plans and
executes research actions, retries failed page fetches, compares each requested
capability, audits supported claims, and returns a cited answer.

The central safety rule is simple: absence of evidence is not evidence of
absence. A capability is reported as `verified_present` or
`verified_unavailable` only when a cited quotation supports that label.
Otherwise, it is `unverified`.

```bash
python main.py "Compare Notion and ClickUp on public API access, official Slack integration, and configurable role-based permissions for a 15-person engineering team."
```

## Current status

The final model configuration is:

- Generator/planner: `qwen2.5:14b`
- Grounding reviewer: `gemma3:4b`

The models come from different families so the reviewer is less likely to repeat
the generator's mistakes. The active evaluation set is numbered 1 through 5.
The latest live evaluation passed 3 of 5 cases. It used 45 LLM calls,
26 tool calls, 31 planning steps, 4 retries, and 2 grounding revisions, and
finished in 89.0 seconds. All factual runs had a final grounding rate of 100%;
factual accuracy was still limited by retrieval coverage, as described below.


## Setup and commands

Prerequisites are Python 3.9+ and a running
[Ollama](https://ollama.com/) installation.

```bash
ollama pull qwen2.5:14b
ollama pull gemma3:4b

python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Run a single comparison:

```bash
.venv/bin/python main.py "your comparison request"
```

Run the complete live evaluation against Ollama and the public web:

```bash
.venv/bin/python evals/run_evals.py
```

Run offline verification without Ollama or network access:

```bash
.venv/bin/python -m pytest tests/ -q
.venv/bin/python tests/verify_cases.py
```

`main.py` prints the final answer, structured cells, sources, statistics, and a
numbered per-node trace. The live evaluator writes:

- `evals/results.md`: readable per-case results, assertions, metrics, and traces
- `evals/run_artifacts.json`: complete answers, cells, evidence, prices, audits,
  injected failures, traces, and model metadata

## Output vocabulary

For every `(product, criterion)` pair, the agent emits one of three labels:

- `verified_present`: a cited quote explicitly establishes the capability
- `verified_unavailable`: a cited quote explicitly states it is unavailable
- `unverified`: checked evidence did not establish either polarity

Pricing is optional. A price is calculated only when the numeric figure appears
in a cited quotation. The calculator accepts arithmetic expressions only and
computes the annual total from the cited per-user monthly price.

## Architecture

The application is a LangGraph state graph with a research loop and a grounding
revision loop:

```text
validate --underspecified--> clarify --> END
   |
  plan <-----------------+
   |  \                  |  gather loop
   |   \--tool--> act ---+
   |
(finish / cap / stall)
   |
compare --> price --> draft --> verify --unsupported--> revise
                                   |  ^                    |
                                   |  +------ verify <-----+
                                   |
                              final_render --> END
```

- **validate** parses products, criteria, team size, and pricing intent. Missing
  products or criteria produce a clarifying question.
- **plan / act** forms the ReAct loop. The planner selects `web_search`,
  `fetch_url`, or `finish`. Evidence and observations are carried through state.
- **act** retries a failed fetch up to the configured limit. Duplicate actions
  are skipped, and repeated no-progress steps terminate through a stall guard.
- **compare** creates one structured cell per product/criterion pair.
- **price** extracts cited figures and uses the arithmetic-only calculator.
- **draft** creates an initial response for the grounding pass.
- **verify / revise** audits asserted cells and deterministically downgrades
  unsupported claims to `unverified`.
- **final_render** renders the user-visible answer directly from the final
  post-verification cells. This prevents rejected claims or citations from
  surviving in stale prose.

`src/state.py` defines the typed graph state. It accumulates evidence,
scratchpad observations, attempted actions, and a human-readable trace across
nodes. Retry, step, stall, revision, LLM-call, and tool-call counters are carried
in the same state.

## Grounding guard

A polarized capability claim survives only if it passes two gates:

1. **Deterministic quotation gate.** The quotation must be a
   whitespace-normalized substring of the cited evidence.
2. **Reviewer entailment gate.** `gemma3:4b` judges from the quotation whether it
   directly supports the product, criterion, and label.

If either gate rejects a cell, `revise` changes its label to `unverified` and
clears its citation and quotation. The final answer is then rendered from those
audited cells rather than trusting the earlier prose draft.

Grounding rate is not factual accuracy. A 100% grounding rate means every final
polarized cell has a surviving citation; it does not guarantee complete
retrieval, official-source compliance, or agreement with a dated gold key.

## Tools and recovery

| Tool | Purpose | Handled failures |
| --- | --- | --- |
| `web_search` | DuckDuckGo search without an API key | empty results, exceptions, irrelevant results in evals |
| `fetch_url` | Requests + BeautifulSoup page extraction | timeout, HTTP errors, parsing failures, bounded retry |
| `calculator` | AST-based arithmetic | rejects names, calls, attributes, and malformed input |

The live evaluation harness consumes `failure_injection` from
`evals/cases.json`:

- Case 2 injects one timeout on the first fetched Miro/Mural URL. It originally
  targeted `mural`, but the planner reliably fetches a `miro`-matching URL
  first and never reached Mural within its step budget, so the injection was
  never exercised. The pattern now targets `miro` instead: the latest run
  shows the injected timeout firing, two retries, and recovery via an
  alternate search, so all five recovery assertions pass.
- Case 5 replaces search output with repeated irrelevant results. The agent must
  terminate within its limits and keep both fictional-product cells unverified.

Injected events are saved in `evals/run_artifacts.json`; retry and fallback
behavior is visible in both artifact traces and `evals/results.md`.

## Evaluation design

There are two evaluation tracks:

- **Factual cases** compare structured cells against the dated hand-labeled key
  in `evals/gold_key.json`.
- **Behavioral cases** enforce explicit assertions for grounding, clarification,
  failure recovery, bounded execution, and safe handling of junk evidence.

`evals/run_evals.py` now evaluates every assertion declared in each case. An
unknown assertion fails closed rather than silently passing. Every case receives
its own `PASS`, `FAIL`, or error section, including assertion-level results.

The five active cases cover:

1. Notion vs. ClickUp capability comparison
2. an injected page timeout and recovery path
3. cited pricing and annual-cost calculation
4. an underspecified request requiring clarification
5. repeated irrelevant results and bounded termination

### Latest live results

Run on 2026-07-21 with `qwen2.5:14b` and `gemma3:4b`:

| Case | Result | Main outcome |
| --- | --- | --- |
| 1 | FAIL | 50% accuracy; retrieval found half the gold cells |
| 2 | PASS | injected Miro fetch timeout observed, retried, and recovered; 5/5 assertions |
| 3 | FAIL | 1/2 expected totals; Notion matched but ClickUp pricing was never retrieved |
| 4 | PASS | clarification with no research or recommendation |
| 5 | PASS | five injected junk searches; bounded, all unverified |

Case 3's failure mode changed from the previous run: this time the agent found
two Notion plans (`$10` Plus and `$20` Business, matching the `$2,400` gold
total) and correctly identified the plan name and billing frequency, but
finished before ever pricing ClickUp, so `calculation_matches_cited_price`
failed on a missing total rather than a wrong one. Same underlying limitation
as Case 1 — the planner can stop before every product has been researched —
showing up as a pricing gap instead of a capability gap.

Live-web results are nondeterministic and documentation changes. The gold key is
dated, two permission quotations are marked weak/unverifiable, and pricing is
especially perishable. Reconfirm the gold sources before treating a factual
score as current truth.

## Model selection

The generator and reviewer are configured in `.env`:

```dotenv
OLLAMA_BASE_URL=http://localhost:11434
GENERATOR_MODEL=qwen2.5:14b
REVIEWER_MODEL=gemma3:4b
```

Several local generators were tested. Qwen 2.5 14B was retained because it gave
the best observed balance of structured JSON reliability, factual behavior, and
latency. Larger generators did not provide a proportional quality improvement:
Qwen 2.5 32B was substantially slower, and Gemma 3 27B would put generator and
reviewer in the same model family.

Model size is not the main remaining bottleneck. Retrieval coverage, source
selection, and pricing-plan selection account for the most visible failures.

## Known limitations and deliberate stopping point

- The planner can finish before every product/criterion pair has received a
  targeted official-source search. This caused under-retrieval in Case 1 and
  a missing ClickUp price in Case 3.
- Official-domain and product/source ownership checks are not yet a deterministic
  grounding gate. A quote can be grounded while coming from a weaker source.
- Pricing extraction can return extra plans and does not yet deterministically
  choose the lowest qualifying paid plan.
- DuckDuckGo snippets can be shallow or irrelevant; fetched pages are stronger
  but may be blocked or JavaScript-rendered.
- The reviewer is still an LLM. The quotation gate is deterministic and
  load-bearing; semantic entailment is not infallible.
- Multi-turn resume is not implemented. Case 4 asks a clarifying question and
  ends; it does not resume the same graph after the user replies.
- Duplicate-action detection is exact-string based rather than semantic.
- Conflicting-source detection and a browser/Playwright fallback were left as
  stretch work.

The project stops here to keep the take-home focused: the agent loop, recovery,
state, grounding, self-correction, ambiguity handling, live evaluation, and
observability are implemented. The next highest-value improvement would be a
deterministic coverage matrix that prevents `finish` until every
product/criterion pair has at least one targeted research attempt.

## Repository map

| Path | Purpose |
| --- | --- |
| `main.py` | CLI and human-readable trace output |
| `src/agent.py` | public entry point and returned artifacts |
| `src/graph.py` | LangGraph topology |
| `src/state.py` | accumulated typed state |
| `src/nodes.py` | planning, action, comparison, audit, revision, final rendering |
| `src/tools.py` | web search, fetch, and calculator tools |
| `src/prompts.py` | model task prompts |
| `evals/cases.json` | five active inputs, assertions, and failure specifications |
| `evals/gold_key.json` | dated factual answer key |
| `evals/run_evals.py` | live scoring, injection, reports, and artifacts |
| `evals/results.md` | latest readable live evaluation |
| `evals/run_artifacts.json` | latest complete case artifacts and traces |
| `tests/verify_cases.py` | deterministic mocked end-to-end checks |
| `tests/test_eval_harness.py` | injection, recovery scoring, and final-render tests |
| `design_note.md` | architecture rationale and tradeoffs |

## Use of AI assistants

An AI coding assistant (ClaudeCode) helped draft scaffolding and implementation changes. I
directed the design, reviewed the output, ran model comparisons, and selected the
final tradeoffs. The decisions retained as project design are the three-state
grounding vocabulary, separate generator and reviewer families, deterministic
quotation check and downgrade, bounded recovery loop, injected failure tests,
assertion-level evaluation, pricing guard, and post-verification deterministic
final rendering.
