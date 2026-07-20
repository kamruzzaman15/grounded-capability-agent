# Evaluation Results

- Generated: 2026-07-19T23:27:40.475166+00:00
- Generator: `qwen2.5:14b`
- Reviewer: `gemma3:4b`

## Case 1 — FAIL

- Track: `factual`
- Status: `active`
- Metrics: accuracy 33%, hallucination 0%, retrieval recall 33%, grounding 100%
- Stats: 14 LLM, 9 tool, 10 steps, 2 retries, 33.4s
- Assertions:
  - FAIL — `all_cells_match_gold`
  - PASS — `all_polarized_cells_have_quote`
  - PASS — `quote_must_entail_label`
  - FAIL — `recommendation_must_follow_priority`
- Trace:
  - validate: products=['Notion', 'ClickUp'] criteria=['public_api_access', 'official_slack_integration', 'configurable_role_based_permissions'] pricing=False
  - plan#1: web_search(Notion ClickUp public API slack integration role based permi)
  - act: search 'Notion ClickUp public API slack integrat' -> 5 results
  - plan#2: fetch_url(https://developers.notion.com/guides/get-started/overview)
  - act: fetch https://developers.notion.com/guides/get -> ok (E6)
  - plan#3: web_search(Notion official documentation public API slack integration r)
  - act: search 'Notion official documentation public API' -> 5 results
  - plan#4: fetch_url(https://developer.clickup.com/docs/Getting+Started)
  - act: fetch retry 1 for https://developer.clickup.com/docs/Getti
  - act: fetch retry 2 for https://developer.clickup.com/docs/Getti
  - act: fetch https://developer.clickup.com/docs/Getti -> FAILED after retries, needs fallback
  - plan#5: web_search(ClickUp official documentation public API slack integration )
  - act: search 'ClickUp official documentation public AP' -> 5 results
  - plan#6: web_search(ClickUp official documentation public API slack integration )
  - act: duplicate action skipped (web_search)
  - plan#7: web_search(ClickUp official documentation for public API slack integrat)
  - act: search 'ClickUp official documentation for publi' -> 5 results
  - plan#8: web_search(ClickUp official documentation for public API slack integrat)
  - act: duplicate action skipped (web_search)
  - plan#9: web_search(ClickUp official documentation for public API slack integrat)
  - act: search 'ClickUp official documentation for publi' -> 5 results
  - plan#10: web_search(ClickUp official documentation for configurable role based p)
  - compare: 6 cells produced
  - price: not requested, skipped
  - draft: answer written
  - verify: gate1 rejected 2, gate2 rejected 0, of 4 asserted
  - revise: downgraded 2 unsupported cell(s) to unverified
  - verify: gate1 rejected 0, gate2 rejected 0, of 2 asserted
  - finalize: answer rendered from verified cells

## Case 2 — PASS

- Track: `factual`
- Status: `active`
- Metrics: accuracy 100%, hallucination 0%, retrieval recall 100%, grounding 100%
- Stats: 6 LLM, 1 tool, 2 steps, 0 retries, 10.6s
- Assertions:
  - PASS — `all_cells_match_gold`
  - PASS — `no_absence_inferred_from_silence`
  - PASS — `quote_must_entail_label`
- Trace:
  - validate: products=['Asana', 'Trello'] criteria=['built_in_time_tracking', 'workload_capacity_view'] pricing=False
  - plan#1: web_search(Asana and Trello built-in time tracking workload capacity vi)
  - act: search 'Asana and Trello built-in time tracking ' -> 5 results
  - plan#2: finish()
  - compare: 4 cells produced
  - price: not requested, skipped
  - draft: answer written
  - verify: gate1 rejected 1, gate2 rejected 1, of 4 asserted
  - revise: downgraded 2 unsupported cell(s) to unverified
  - verify: gate1 rejected 0, gate2 rejected 0, of 2 asserted
  - finalize: answer rendered from verified cells

## Case 3 — PASS

- Track: `behavioral`
- Status: `active`
- Stats: 8 LLM, 7 tool, 6 steps, 2 retries, 16.8s
- Assertions:
  - PASS — `all_unresolved_cells_marked_unverified`
  - PASS — `no_present_or_unavailable_without_quote`
  - PASS — `absence_of_evidence_not_treated_as_absence`
  - PASS — `all_final_claims_grounded`
- Trace:
  - validate: products=['Linear', 'Height'] criteria=['end_to_end_encryption_of_document_content', 'fedramp_authorization'] pricing=False
  - plan#1: web_search(FedRAMP Linear Height product end to end encryption document)
  - act: search 'FedRAMP Linear Height product end to end' -> 5 results
  - plan#2: web_search(FedRAMP Linear Height product security features end to end e)
  - act: search 'FedRAMP Linear Height product security f' -> 5 results
  - plan#3: fetch_url(https://marketplace.fedramp.gov/)
  - act: fetch https://marketplace.fedramp.gov/ -> ok (E11)
  - plan#4: fetch_url(https://marketplace.fedramp.gov/products/linear)
  - act: fetch retry 1 for https://marketplace.fedramp.gov/products
  - act: fetch retry 2 for https://marketplace.fedramp.gov/products
  - act: fetch https://marketplace.fedramp.gov/products -> FAILED after retries, needs fallback
  - plan#5: web_search(FedRAMP Linear Height cloud products security features end t)
  - act: search 'FedRAMP Linear Height cloud products sec' -> 5 results
  - plan#6: finish()
  - compare: 4 cells produced
  - price: not requested, skipped
  - draft: answer written
  - verify: gate1 rejected 0, gate2 rejected 0, of 0 asserted
  - finalize: answer rendered from verified cells

## Case 4 — FAIL

- Track: `behavioral`
- Status: `active`
- Stats: 10 LLM, 7 tool, 7 steps, 2 retries, 18.6s
- Assertions:
  - FAIL — `failure_detected`
  - PASS — `retry_count_at_least`
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
  - plan#4: web_search(Miro help center real time collaboration Slack integration)
  - act: search 'Miro help center real time collaboration' -> 5 results
  - plan#5: fetch_url(https://help.miro.com/hc/en-us/articles/360017572494-Slack)
  - act: fetch retry 1 for https://help.miro.com/hc/en-us/articles/
  - act: fetch retry 2 for https://help.miro.com/hc/en-us/articles/
  - act: fetch https://help.miro.com/hc/en-us/articles/ -> FAILED after retries, needs fallback
  - plan#6: web_search(Miro real time collaboration Slack integration official docu)
  - act: duplicate action skipped (web_search)
  - plan#7: web_search(Miro real time collaboration Slack integration official docu)
  - compare: 4 cells produced
  - price: not requested, skipped
  - draft: answer written
  - verify: gate1 rejected 0, gate2 rejected 0, of 2 asserted
  - finalize: answer rendered from verified cells

## Case 5 — FAIL

- Track: `factual`
- Status: `active`
- Pricing: 2/2 expected annual costs matched
- Stats: 11 LLM, 5 tool, 6 steps, 0 retries, 23.8s
- Assertions:
  - FAIL — `price_has_supporting_quote`
  - FAIL — `billing_frequency_identified`
  - FAIL — `plan_name_identified`
  - PASS — `calculation_matches_cited_price`
  - PASS — `calculator_tool_used`
  - PASS — `unverified_if_price_cannot_be_confirmed`
- Trace:
  - validate: products=['Notion', 'ClickUp'] criteria=['collaboration_capabilities', 'annual_cost_for_20_users'] pricing=True
  - plan#1: web_search(Notion ClickUp collaboration capabilities annual cost 20 use)
  - act: search 'Notion ClickUp collaboration capabilitie' -> 5 results
  - plan#2: fetch_url(https://www.joinsecret.com/compare/clickup-vs-notion)
  - act: fetch https://www.joinsecret.com/compare/click -> ok (E6)
  - plan#3: fetch_url(https://www.cloudwards.net/clickup-vs-notion/)
  - act: fetch https://www.cloudwards.net/clickup-vs-no -> ok (E7)
  - plan#4: web_search(Notion ClickUp annual cost for 20 users)
  - act: search 'Notion ClickUp annual cost for 20 users' -> 5 results
  - plan#5: fetch_url(https://comparetiers.com/blog/notion-vs-clickup-pricing)
  - act: fetch https://comparetiers.com/blog/notion-vs- -> ok (E13)
  - plan#6: finish()
  - compare: 4 cells produced
  - price: 4 verified
  - draft: answer written
  - verify: gate1 rejected 1, gate2 rejected 0, of 2 asserted
  - revise: downgraded 1 unsupported cell(s) to unverified
  - verify: gate1 rejected 0, gate2 rejected 0, of 1 asserted
  - finalize: answer rendered from verified cells

## Case 6 — PASS

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

## Case 7 — FAIL

- Track: `factual`
- Status: `active`
- Metrics: accuracy 17%, hallucination 0%, retrieval recall 17%, grounding 100%
- Stats: 11 LLM, 5 tool, 8 steps, 0 retries, 20.9s
- Assertions:
  - FAIL — `all_cells_match_gold`
  - PASS — `all_polarized_cells_have_quote`
  - PASS — `quote_must_entail_label`
- Trace:
  - validate: products=['Figma', 'Canva'] criteria=['developer_api_access', 'version_history', 'configurable_team_permissions'] pricing=False
  - plan#1: web_search(Figma developer API access version history configurable team)
  - act: search 'Figma developer API access version histo' -> 5 results
  - plan#2: web_search(Figma developer documentation)
  - act: search 'Figma developer documentation' -> 5 results
  - plan#3: fetch_url(https://developers.figma.com/)
  - act: fetch https://developers.figma.com/ -> ok (E11)
  - plan#4: fetch_url(https://developers.figma.com/docs/rest-api/)
  - act: fetch https://developers.figma.com/docs/rest-a -> ok (E12)
  - plan#5: web_search(Figma developer documentation version history configurable t)
  - act: search 'Figma developer documentation version hi' -> 5 results
  - plan#6: web_search(Figma developer documentation version history configurable t)
  - act: duplicate action skipped (web_search)
  - plan#7: web_search(Figma developer documentation version history configurable t)
  - act: duplicate action skipped (web_search)
  - plan#8: web_search(Figma developer documentation version history configurable t)
  - compare: 6 cells produced
  - price: not requested, skipped
  - draft: answer written
  - verify: gate1 rejected 0, gate2 rejected 0, of 1 asserted
  - finalize: answer rendered from verified cells

## Case 8 — PASS

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

