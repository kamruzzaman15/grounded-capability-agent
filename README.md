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
the generator's mistakes. The latest hardened live evaluation passed 5 of 8
cases. It used 72 LLM calls, 45 tool calls, 51 planning steps, 7 retries, and
finished in 135.9 seconds. All factual runs had a final grounding rate of 100%;
factual accuracy was still limited by retrieval coverage, as described below.

Offline verification currently passes:

- 12/12 unit tests
- 10/10 deterministic mocked evaluation checks

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

- Case 4 injects one timeout for a Mural page. The latest run detected it,
  retried once, recovered, and passed all five recovery assertions.
- Case 8 replaces search output with repeated irrelevant results. The agent must
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

Metrics are:

- capability accuracy: cells whose label matches the gold key
- hallucination rate: polarized cells contradicting the gold key
- retrieval recall: answerable gold cells for which evidence was retrieved
- grounding rate: final polarized cells retaining citations
- operational statistics: LLM calls, tool calls, steps, retries, revisions, and
  wall-clock duration

The eight cases cover:

1. Notion vs. ClickUp capability comparison
2. present-vs-unverified behavior for Asana and Trello
3. undocumented security capabilities that must remain unverified
4. an injected page timeout and recovery path
5. cited pricing and annual-cost calculation
6. an underspecified request requiring clarification
7. a different product category: Figma vs. Canva
8. repeated irrelevant results and bounded termination

### Latest live results

Run on 2026-07-19 with `qwen2.5:14b` and `gemma3:4b`:

| Case | Result | Main outcome |
| --- | --- | --- |
| 1 | FAIL | 33% accuracy, 0% hallucination; retrieval missed four gold cells |
| 2 | PASS | 100% accuracy, recall, and grounding |
| 3 | PASS | all four unresolved security cells remained unverified |
| 4 | PASS | injected timeout observed; 1 retry; 5/5 assertions |
| 5 | FAIL | both expected totals appeared, but plan/billing/selection assertions failed |
| 6 | PASS | clarification with no research or recommendation |
| 7 | FAIL | 33% accuracy; research under-covered Canva |
| 8 | PASS | five injected junk searches; bounded, all unverified |

Case 5 exposed an important failure: the model extracted four price options
instead of selecting exactly the lowest paid plan per product. Although the
expected `$2,400` and `$1,680` totals appeared, the case correctly failed because
plan names, annual billing context, and plan selection were incomplete.

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
  targeted official-source search. This caused under-retrieval in Cases 1 and 7.
- Official-domain and product/source ownership checks are not yet a deterministic
  grounding gate. A quote can be grounded while coming from a weaker source.
- Pricing extraction can return extra plans and does not yet deterministically
  choose the lowest qualifying paid plan.
- DuckDuckGo snippets can be shallow or irrelevant; fetched pages are stronger
  but may be blocked or JavaScript-rendered.
- The reviewer is still an LLM. The quotation gate is deterministic and
  load-bearing; semantic entailment is not infallible.
- Multi-turn resume is not implemented. Case 6 asks a clarifying question and
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
| `evals/cases.json` | eight inputs, assertions, and failure specifications |
| `evals/gold_key.json` | dated factual answer key |
| `evals/run_evals.py` | live scoring, injection, reports, and artifacts |
| `evals/results.md` | latest readable live evaluation |
| `evals/run_artifacts.json` | latest complete case artifacts and traces |
| `tests/verify_cases.py` | deterministic mocked end-to-end checks |
| `tests/test_eval_harness.py` | injection, recovery scoring, and final-render tests |
| `design_note.md` | architecture rationale and tradeoffs |

## Use of AI assistants

An AI coding assistant helped draft scaffolding and implementation changes. I
directed the design, reviewed the output, ran model comparisons, and selected the
final tradeoffs. The decisions retained as project design are the three-state
grounding vocabulary, separate generator and reviewer families, deterministic
quotation check and downgrade, bounded recovery loop, injected failure tests,
assertion-level evaluation, pricing guard, and post-verification deterministic
final rendering.
