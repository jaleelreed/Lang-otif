"""Graph wiring: intake -> scoring -> (conditional) -> escalation | explainer.

SqliteSaver checkpointer keyed by thread_id so interrupted runs resume across
process restarts.
"""
import sqlite3

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from otif_graph.nodes.escalation import escalation
from otif_graph.nodes.explainer import make_explainer
from otif_graph.nodes.intake import make_intake
from otif_graph.nodes.scoring import scoring
from otif_graph.state import GraphState


def route_after_intake(state: GraphState) -> str:
    return "escalation" if state.batch is None else "scoring"


def route_after_scoring(state: GraphState) -> str:
    return "escalation" if state.needs_review else "explainer"


def route_after_escalation(state: GraphState) -> str:
    if state.review_decision == "approve":
        return "explainer"
    if state.review_decision == "reject":
        return END
    return "intake"  # rescore


def build_graph(llm, db_path: str):
    g = StateGraph(GraphState)
    g.add_node("intake", make_intake(llm))
    g.add_node("scoring", scoring)
    g.add_node("escalation", escalation)
    g.add_node("explainer", make_explainer(llm))
    g.set_entry_point("intake")
    g.add_conditional_edges("intake", route_after_intake,
                            {"scoring": "scoring", "escalation": "escalation"})
    g.add_conditional_edges("scoring", route_after_scoring,
                            {"escalation": "escalation", "explainer": "explainer"})
    g.add_conditional_edges("escalation", route_after_escalation,
                            {"intake": "intake", "explainer": "explainer", END: END})
    g.add_edge("explainer", END)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    # explicit allowlist so our pydantic state round-trips checkpoints without
    # the unregistered-type deprecation warning
    serde = JsonPlusSerializer(allowed_msgpack_modules=[
        ("otif_graph.state", "ShipmentBatch"),
        ("otif_graph.state", "ShipmentRecord"),
        ("otif_graph.state", "OtifResult"),
        ("otif_graph.state", "ScoringPolicy"),
        ("otif_graph.state", "GraphState"),
    ])
    return g.compile(checkpointer=SqliteSaver(conn, serde=serde))
