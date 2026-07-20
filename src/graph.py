r"""LangGraph state graph.

    validate --underspecified--> clarify --> END
       |
     (specified)
       |
      plan <----------------+
       |  \                 | (gather loop; stops on finish, step cap, or stall)
       |   \--tool--> act --+
       |
    (finish / cap / stall)
       |
    compare --> price --> draft --> verify --unsupported--> revise
                                       |  ^                    |
                                       |  \------ verify <-----/  (two-gate fix
                                       |                           loop, capped)
                                    finalize --> END

Two loops (gather and verify/revise), two conditional branches (validate,
verify). Caps live in the routing functions so they are inspectable and
unit-testable in one place. See design_note.md for why LangGraph.
"""

from langgraph.graph import END, StateGraph

from . import nodes
from .state import AgentState


def build_graph():
    g = StateGraph(AgentState)
    for name, fn in [
        ("validate", nodes.validate_node), ("clarify", nodes.clarify_node),
        ("plan", nodes.plan_node), ("act", nodes.act_node),
        ("compare", nodes.compare_node), ("price", nodes.price_node),
        ("draft", nodes.draft_node), ("verify", nodes.verify_node),
        ("revise", nodes.revise_node), ("finalize", nodes.finalize_node),
    ]:
        g.add_node(name, fn)

    g.set_entry_point("validate")
    g.add_conditional_edges("validate", nodes.route_after_validate,
                            {"clarify": "clarify", "plan": "plan"})
    g.add_edge("clarify", END)
    g.add_conditional_edges("plan", nodes.route_after_plan,
                            {"act": "act", "compare": "compare"})
    g.add_edge("act", "plan")
    g.add_edge("compare", "price")
    g.add_edge("price", "draft")
    g.add_edge("draft", "verify")
    g.add_conditional_edges("verify", nodes.route_after_verify,
                            {"revise": "revise", "finalize": "finalize"})
    g.add_edge("revise", "verify")
    g.add_edge("finalize", END)
    return g.compile()
