"""Prompt builders. Each system prompt begins with a [TASK: ...] tag so tests
can route a mock LLM deterministically and each call's job stays legible.
"""

TAG_PARSE = "[TASK: PARSE_GOAL]"
TAG_PLAN = "[TASK: PLAN_ACTION]"
TAG_COMPARE = "[TASK: COMPARE]"
TAG_PRICE = "[TASK: PRICE]"
TAG_ENTAIL = "[TASK: ENTAILMENT]"
TAG_DRAFT = "[TASK: DRAFT]"


def parse_prompt(goal):
    system = (
        f"{TAG_PARSE}\n"
        "Extract the comparison request into JSON. Fields: products (list of "
        "product names or URLs, usually two), criteria (list of capabilities to "
        "compare), team_size (integer or null), wants_pricing (true only if the "
        'user asks for cost or price). Respond with ONLY JSON: {"products":[],'
        '"criteria":[],"team_size":null,"wants_pricing":false}.'
    )
    return system, f"REQUEST: {goal}"


_PLAN_TOOLS = """Actions:
- web_search : action_input = a search query. Prefer official docs / help center.
- fetch_url  : action_input = a URL from a prior search result.
- finish     : action_input = "". Choose this once evidence covers the criteria
               or no further official source is likely.
"""


def plan_prompt(state):
    parsed = state["parsed"]
    evidence = "\n".join(
        f"{e['id']} [{e['source']}]: {e['content'][:180]}" for e in state["evidence"]
    ) or "(none yet)"
    recent = "\n".join(state["scratchpad"][-6:]) or "(empty)"
    system = (
        f"{TAG_PLAN}\n"
        "You are a research planner. Pick the single next action that best "
        "covers the requested criteria with official-source evidence. If the "
        "last action failed, retry once or try an alternate official source. Do "
        "not repeat a search or fetch you already ran. Choose finish when the "
        'criteria are covered or no further source is likely. Respond with ONLY '
        'JSON: {"thought":str,"action":one of [web_search, fetch_url, finish],'
        '"action_input":str}.'
    )
    user = (
        f"PRODUCTS: {parsed.get('products')}\n"
        f"CRITERIA: {parsed.get('criteria')}\n\n"
        f"EVIDENCE SO FAR:\n{evidence}\n\n"
        f"RECENT STEPS:\n{recent}\n\n{_PLAN_TOOLS}\nReturn the next action."
    )
    return system, user


def compare_prompt(state):
    parsed = state["parsed"]
    evidence = "\n".join(
        f"{e['id']} [{e['source']}]: {e['content'][:400]}" for e in state["evidence"]
    ) or "(none)"
    system = (
        f"{TAG_COMPARE}\n"
        "Build a capability comparison grounded ONLY in the evidence. For each "
        "product and each criterion, output one cell. Use 'verified_present' or "
        "'verified_unavailable' ONLY when a specific evidence quote explicitly "
        "states it; then set citation_id to that evidence id and quote to the "
        "exact supporting substring. Absence of any mention is NOT "
        "'verified_unavailable' -- if no evidence explicitly speaks to the "
        "criterion, use 'unverified' with empty citation_id and quote. Respond "
        'with ONLY JSON: {"cells":[{"product":str,"criterion":str,"label":'
        '"verified_present|verified_unavailable|unverified","citation_id":str,'
        '"quote":str}]}.'
    )
    user = (
        f"PRODUCTS: {parsed.get('products')}\n"
        f"CRITERIA: {parsed.get('criteria')}\n\n"
        f"EVIDENCE:\n{evidence}\n\nProduce one cell per product-criterion pair."
    )
    return system, user


def price_prompt(state):
    parsed = state["parsed"]
    evidence = "\n".join(
        f"{e['id']} [{e['source']}]: {e['content'][:400]}" for e in state["evidence"]
    ) or "(none)"
    system = (
        f"{TAG_PRICE}\n"
        "Extract the per-user monthly price for each product from the evidence "
        "ONLY. For each product give per_user_monthly (number), plan_name, "
        "citation_id, and the exact quote containing that number. If no evidence "
        'states a price, set per_user_monthly to null. Respond with ONLY JSON: '
        '{"prices":[{"product":str,"per_user_monthly":number_or_null,"plan_name":'
        'str,"citation_id":str,"quote":str}]}.'
    )
    return system, f"PRODUCTS: {parsed.get('products')}\n\nEVIDENCE:\n{evidence}"


def entailment_prompt(cells):
    """Gate two: does each cited quote actually entail its label for the
    criterion? Judged by the reviewer model, quote-only, no outside knowledge.
    """
    listing = "\n".join(
        f"- product={c['product']} | criterion={c['criterion']} | label={c['label']} "
        f"| quote=\"{c['quote'][:200]}\""
        for c in cells
    ) or "(none)"
    system = (
        f"{TAG_ENTAIL}\n"
        "You are a strict entailment auditor. For each item, judge ONLY from the "
        "quote whether it supports the stated label for that product and "
        "criterion. 'supported' means the quote directly establishes the claim; "
        "'insufficient' means the quote is about something else, is only "
        "promotional, or does not establish the specific capability. Use no "
        'outside knowledge. Respond with ONLY JSON: {"verdicts":[{"product":str,'
        '"criterion":str,"verdict":"supported|insufficient","note":str}]}.'
    )
    return system, f"ITEMS:\n{listing}\n\nJudge each item."


def draft_prompt(state):
    parsed = state["parsed"]
    comparison = state["comparison"]
    cost = state.get("cost") or {}
    cells_txt = "\n".join(
        f"- {c['product']} / {c['criterion']}: {c['label']}"
        + (f" [{c['citation_id']}]" if c["citation_id"] else "")
        for c in comparison.get("cells", [])
    )
    cost_txt = "COST:\n" + "\n".join(cost["lines"]) if cost.get("lines") else ""
    system = (
        f"{TAG_DRAFT}\n"
        "Write a concise capability comparison from the structured cells ONLY. "
        "State verified_present, verified_unavailable, or unverified per "
        "criterion, keeping the [E#] citations. List unverified criteria "
        "explicitly rather than glossing over them. End with a short "
        "recommendation that follows from the cells and the team size, and note "
        "it depends on the user's priorities. Do not introduce facts not in the "
        "cells."
    )
    user = (
        f"GOAL: {state['goal']}\nTEAM SIZE: {parsed.get('team_size')}\n\n"
        f"CELLS:\n{cells_txt}\n\n{cost_txt}\n\nWrite the answer."
    )
    return system, user
