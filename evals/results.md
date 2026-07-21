# Evaluation Results

- Generated: 2026-07-21T07:01:59.847102+00:00
- Generator: `qwen2.5:14b`
- Reviewer: `gemma3:4b`

## Case 1 — FAIL

- Track: `factual`
- Status: `active`
- Metrics: accuracy 50%, hallucination 0%, retrieval recall 50%, grounding 100%
- Stats: 13 LLM, 10 tool, 9 steps, 2 retries, 34.1s
- Assertions:
  - FAIL — `all_cells_match_gold`
  - PASS — `all_polarized_cells_have_quote`
  - PASS — `quote_must_entail_label`
  - FAIL — `recommendation_must_follow_priority`
- Trace:
  - validate: products=['Notion', 'ClickUp'] criteria=['public_api_access', 'official_slack_integration', 'configurable_role_based_permissions'] pricing=False
  - plan#1: web_search(Notion ClickUp public API slack integration role based permi)
  - act: search 'Notion ClickUp public API slack integrat' -> 5 results
  - plan#2: fetch_url(https://developer.clickup.com/)
  - act: fetch https://developer.clickup.com/ -> ok (E6)
  - plan#3: web_search(ClickUp official documentation public API slack integration )
  - act: search 'ClickUp official documentation public AP' -> 5 results
  - plan#4: fetch_url(https://help.clickup.com/hc/en-us/articles/6304922742295-Int)
  - act: fetch retry 1 for https://help.clickup.com/hc/en-us/articl
  - act: fetch retry 2 for https://help.clickup.com/hc/en-us/articl
  - act: fetch https://help.clickup.com/hc/en-us/articl -> FAILED after retries, needs fallback
  - plan#5: web_search(ClickUp official slack integration documentation)
  - act: search 'ClickUp official slack integration docum' -> 5 results
  - plan#6: web_search(Notion official slack integration documentation)
  - act: search 'Notion official slack integration docume' -> 5 results
  - plan#7: fetch_url(https://www.notion.com/help/slack)
  - act: fetch https://www.notion.com/help/slack -> ok (E22)
  - plan#8: web_search(ClickUp official public API documentation)
  - act: search 'ClickUp official public API documentatio' -> 5 results
  - plan#9: finish()
  - compare: 6 cells produced
  - price: not requested, skipped
  - draft: answer written
  - verify: gate1 rejected 1, gate2 rejected 0, of 4 asserted
  - revise: downgraded 1 unsupported cell(s) to unverified
  - verify: gate1 rejected 0, gate2 rejected 0, of 3 asserted
  - finalize: answer rendered from verified cells

## Case 2 — PASS

- Track: `behavioral`
- Status: `active`
- Stats: 14 LLM, 8 tool, 10 steps, 2 retries, 27.3s
- Injected failures/results: 1
- Assertions:
  - PASS — `failure_detected`
  - PASS — `retry_count_at_least`
  - PASS — `different_query_or_source_used`
  - PASS — `no_fabricated_claims`
  - PASS — `run_terminates_within_step_limit`
- Trace:
  - validate: products=['Miro', 'Mural'] criteria=['real_time_collaboration', 'official_slack_integration'] pricing=False
  - plan#1: web_search(Miro real time collaboration Slack integration official docu)
  - act: search 'Miro real time collaboration Slack integ' -> 5 results
  - plan#2: fetch_url(https://www.g2.com/products/miro/reviews)
  - act: fetch retry 1 for https://www.g2.com/products/miro/reviews
  - act: fetch retry 2 for https://www.g2.com/products/miro/reviews
  - act: fetch https://www.g2.com/products/miro/reviews -> FAILED after retries, needs fallback
  - plan#3: web_search(Miro official slack integration documentation)
  - act: search 'Miro official slack integration document' -> 5 results
  - plan#4: web_search(MURAL official slack integration documentation)
  - act: search 'MURAL official slack integration documen' -> 5 results
  - plan#5: web_search(MURAL real-time collaboration Slack integration official doc)
  - act: search 'MURAL real-time collaboration Slack inte' -> 5 results
  - plan#6: web_search(MURAL real-time collaboration Slack integration official doc)
  - act: duplicate action skipped (web_search)
  - plan#7: web_search(MURAL real-time collaboration Slack integration official sit)
  - act: search 'MURAL real-time collaboration Slack inte' -> 5 results
  - plan#8: web_search(MURAL real-time collaboration Slack integration official sit)
  - act: duplicate action skipped (web_search)
  - plan#9: web_search(MURAL real-time collaboration Slack integration official sit)
  - act: duplicate action skipped (web_search)
  - plan#10: web_search(MURAL real-time collaboration Slack integration official doc)
  - compare: 4 cells produced
  - price: not requested, skipped
  - draft: answer written
  - verify: gate1 rejected 0, gate2 rejected 1, of 3 asserted
  - revise: downgraded 1 unsupported cell(s) to unverified
  - verify: gate1 rejected 0, gate2 rejected 0, of 2 asserted
  - finalize: answer rendered from verified cells

## Case 3 — FAIL

- Track: `factual`
- Status: `active`
- Pricing: 1/2 expected annual costs matched
- Stats: 9 LLM, 3 tool, 5 steps, 0 retries, 17.1s
- Assertions:
  - PASS — `price_has_supporting_quote`
  - PASS — `billing_frequency_identified`
  - PASS — `plan_name_identified`
  - FAIL — `calculation_matches_cited_price`
  - PASS — `calculator_tool_used`
  - PASS — `unverified_if_price_cannot_be_confirmed`
- Trace:
  - validate: products=['Notion', 'ClickUp'] criteria=['collaboration_capabilities', 'annual_cost_for_20_users'] pricing=True
  - plan#1: web_search(Notion ClickUp collaboration capabilities annual cost 20 use)
  - act: search 'Notion ClickUp collaboration capabilitie' -> 5 results
  - plan#2: web_search(Notion ClickUp collaboration features pricing plan 20 users)
  - act: search 'Notion ClickUp collaboration features pr' -> 5 results
  - plan#3: fetch_url(https://www.fahimai.com/notion-vs-clickup)
  - act: fetch https://www.fahimai.com/notion-vs-clicku -> ok (E11)
  - plan#4: fetch_url(https://www.fahimai.com/notion-vs-clickup)
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
- Stats: 9 LLM, 5 tool, 7 steps, 0 retries, 10.5s
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

