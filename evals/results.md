# Evaluation Results

- Generated: 2026-07-21T06:40:23.071835+00:00
- Generator: `qwen2.5:14b`
- Reviewer: `gemma3:4b`

## Case 1 — FAIL

- Track: `factual`
- Status: `active`
- Metrics: accuracy 17%, hallucination 0%, retrieval recall 17%, grounding 100%
- Stats: 12 LLM, 10 tool, 9 steps, 4 retries, 25.8s
- Assertions:
  - FAIL — `all_cells_match_gold`
  - PASS — `all_polarized_cells_have_quote`
  - PASS — `quote_must_entail_label`
  - FAIL — `recommendation_must_follow_priority`
- Trace:
  - validate: products=['Notion', 'ClickUp'] criteria=['public_api_access', 'official_slack_integration', 'configurable_role_based_permissions'] pricing=False
  - plan#1: web_search(Notion ClickUp public API slack integration role based permi)
  - act: search 'Notion ClickUp public API slack integrat' -> 5 results
  - plan#2: web_search(Notion official documentation public API slack integration r)
  - act: search 'Notion official documentation public API' -> 5 results
  - plan#3: fetch_url(https://developers.notion.com/docs)
  - act: fetch retry 1 for https://developers.notion.com/docs
  - act: fetch retry 2 for https://developers.notion.com/docs
  - act: fetch https://developers.notion.com/docs -> FAILED after retries, needs fallback
  - plan#4: web_search(Notion ClickUp official developer documentation)
  - act: search 'Notion ClickUp official developer docume' -> 5 results
  - plan#5: fetch_url(https://developer.clickup.com/docs/Getting+Started)
  - act: fetch retry 1 for https://developer.clickup.com/docs/Getti
  - act: fetch retry 2 for https://developer.clickup.com/docs/Getti
  - act: fetch https://developer.clickup.com/docs/Getti -> FAILED after retries, needs fallback
  - plan#6: web_search(Notion ClickUp developer documentation official site)
  - act: search 'Notion ClickUp developer documentation o' -> 5 results
  - plan#7: fetch_url(https://developers.notion.com/docs)
  - act: duplicate action skipped (fetch_url)
  - plan#8: fetch_url(https://developers.notion.com/docs)
  - act: duplicate action skipped (fetch_url)
  - plan#9: fetch_url(https://developer.clickup.com/)
  - compare: 6 cells produced
  - price: not requested, skipped
  - draft: answer written
  - verify: gate1 rejected 0, gate2 rejected 0, of 1 asserted
  - finalize: answer rendered from verified cells

## Case 2 — FAIL

- Track: `behavioral`
- Status: `active`
- Stats: 9 LLM, 3 tool, 6 steps, 0 retries, 12.6s
- Assertions:
  - FAIL — `failure_detected`
  - FAIL — `retry_count_at_least`
  - PASS — `different_query_or_source_used`
  - PASS — `no_fabricated_claims`
  - PASS — `run_terminates_within_step_limit`
- Trace:
  - validate: products=['Miro', 'Mural'] criteria=['real_time_collaboration', 'official_slack_integration'] pricing=False
  - plan#1: web_search(Miro real time collaboration Slack integration official docu)
  - act: search 'Miro real time collaboration Slack integ' -> 5 results
  - plan#2: fetch_url(https://miro.com/)
  - act: fetch https://miro.com/ -> ok (E6)
  - plan#3: web_search(Miro real time collaboration Slack integration official help)
  - act: search 'Miro real time collaboration Slack integ' -> 5 results
  - plan#4: web_search(Miro real time collaboration Slack integration official help)
  - act: duplicate action skipped (web_search)
  - plan#5: web_search(Miro real time collaboration Slack integration official docu)
  - act: duplicate action skipped (web_search)
  - plan#6: web_search(Miro real time collaboration Slack integration official docu)
  - compare: 4 cells produced
  - price: not requested, skipped
  - draft: answer written
  - verify: gate1 rejected 0, gate2 rejected 0, of 1 asserted
  - finalize: answer rendered from verified cells

## Case 3 — FAIL

- Track: `factual`
- Status: `active`
- Pricing: 1/2 expected annual costs matched
- Stats: 9 LLM, 3 tool, 5 steps, 0 retries, 16.4s
- Assertions:
  - PASS — `price_has_supporting_quote`
  - PASS — `billing_frequency_identified`
  - FAIL — `plan_name_identified`
  - FAIL — `calculation_matches_cited_price`
  - PASS — `calculator_tool_used`
  - PASS — `unverified_if_price_cannot_be_confirmed`
- Trace:
  - validate: products=['Notion', 'ClickUp'] criteria=['collaboration_capabilities', 'annual_cost_for_20_users'] pricing=True
  - plan#1: web_search(Notion ClickUp collaboration capabilities annual cost 20 use)
  - act: search 'Notion ClickUp collaboration capabilitie' -> 5 results
  - plan#2: fetch_url(https://www.cloudwards.net/clickup-vs-notion/)
  - act: fetch https://www.cloudwards.net/clickup-vs-no -> ok (E6)
  - plan#3: fetch_url(https://www.joinsecret.com/compare/clickup-vs-notion)
  - act: fetch https://www.joinsecret.com/compare/click -> ok (E7)
  - plan#4: fetch_url(https://www.joinsecret.com/compare/clickup-vs-notion)
  - act: duplicate action skipped (fetch_url)
  - plan#5: finish()
  - compare: 4 cells produced
  - price: 2 verified
  - draft: answer written
  - verify: gate1 rejected 0, gate2 rejected 0, of 2 asserted
  - finalize: answer rendered from verified cells

## Case 4 — PASS

- Track: `behavioral`
- Status: `known_gap`
- Stats: 0 LLM, 0 tool, 0 steps, 0 retries, 0.0s
- Assertions:
  - PASS — `asks_clarifying_question`
  - PASS — `does_not_start_research`
  - PASS — `does_not_make_recommendation`
- Trace:
  - validate: products=['Notion', 'ClickUp'] criteria=[] pricing=False
  - clarify: request underspecified, asking for criteria/products

## Case 5 — PASS

- Track: `behavioral`
- Status: `active`
- Stats: 9 LLM, 5 tool, 7 steps, 0 retries, 10.4s
- Injected failures/results: 5
- Assertions:
  - PASS — `criterion_marked_unverified`
  - PASS — `no_present_or_unavailable_claim`
  - PASS — `tool_calls_within_limit`
  - PASS — `graph_steps_within_limit`
  - PASS — `run_terminates`
- Trace:
  - validate: products=['Product Alpha', 'Product Beta'] criteria=['quantum_resistant_document_encryption'] pricing=False
  - plan#1: web_search(Product Alpha Product Beta quantum resistant document encryp)
  - act: search 'Product Alpha Product Beta quantum resis' -> 1 results
  - plan#2: web_search(Product Alpha Product Beta quantum resistant document encryp)
  - act: search 'Product Alpha Product Beta quantum resis' -> 1 results
  - plan#3: web_search(Product Alpha Product Beta quantum resistant document encryp)
  - act: duplicate action skipped (web_search)
  - plan#4: web_search(Product Alpha Product Beta quantum resistant document encryp)
  - act: search 'Product Alpha Product Beta quantum resis' -> 1 results
  - plan#5: web_search(Product Alpha Product Beta quantum resistant document encryp)
  - act: search 'Product Alpha Product Beta quantum resis' -> 1 results
  - plan#6: web_search(Product Alpha Product Beta quantum resistant document encryp)
  - act: search 'Product Alpha Product Beta quantum resis' -> 1 results
  - plan#7: finish()
  - compare: 2 cells produced
  - price: not requested, skipped
  - draft: answer written
  - verify: gate1 rejected 0, gate2 rejected 0, of 0 asserted
  - finalize: answer rendered from verified cells

