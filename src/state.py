"""Graph state. scratchpad, trace, evidence, and seen_actions accumulate across
steps via the operator.add reducer, so each node returns only its delta.
Everything else is replace-on-write, safe because nodes run sequentially.

trace is the observability hook: every node appends one human-readable line, so
a finished run carries its own step-by-step log.
"""

import operator
from typing import Annotated, Any, Dict, List, TypedDict


class AgentState(TypedDict):
    goal: str
    parsed: Dict[str, Any]

    scratchpad: Annotated[List[str], operator.add]
    trace: Annotated[List[str], operator.add]
    evidence: Annotated[List[Dict[str, Any]], operator.add]
    seen_actions: Annotated[List[str], operator.add]

    next_action: Dict[str, Any]
    step: int
    retries: int
    stall: int

    comparison: Dict[str, Any]
    prices: List[Dict[str, Any]]
    cost: Dict[str, Any]

    draft: str
    audit: Dict[str, Any]
    revisions: int

    clarifying_question: str
    final: Dict[str, Any]

    llm_calls: int
    tool_calls: int
