"""Typed contracts between graph steps. Every LLM output is validated here
before it can drive control flow, so a malformed generation degrades to a safe
default instead of crashing the graph.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel

Label = Literal["verified_present", "verified_unavailable", "unverified"]


class ParsedGoal(BaseModel):
    products: List[str] = []
    criteria: List[str] = []
    team_size: Optional[int] = None
    wants_pricing: bool = False


class AgentAction(BaseModel):
    thought: str = ""
    action: Literal["web_search", "fetch_url", "finish"]
    action_input: str = ""


class Cell(BaseModel):
    """One (product, criterion) result. verified_present and verified_unavailable
    require a citation and a supporting quote; unverified carries neither.
    """

    product: str
    criterion: str
    label: Label = "unverified"
    citation_id: str = ""
    quote: str = ""


class Comparison(BaseModel):
    cells: List[Cell] = []


class PriceFinding(BaseModel):
    product: str
    per_user_monthly: Optional[float] = None
    plan_name: str = ""
    citation_id: str = ""
    quote: str = ""


class EntailmentVerdict(BaseModel):
    product: str
    criterion: str
    verdict: Literal["supported", "insufficient"] = "insufficient"
    note: str = ""


class EntailmentReport(BaseModel):
    verdicts: List[EntailmentVerdict] = []
