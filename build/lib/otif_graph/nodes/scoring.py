"""Scoring node: calls the deterministic engine and nothing else.

This file must never import llm, ollama, requests, langchain, or langgraph.
Enforced by tests/test_no_llm_in_math.py.
"""
from otif_graph import engine
from otif_graph.state import GraphState, audit


def scoring(state: GraphState) -> dict:
    policy = state.policy or engine.DEFAULT_POLICY
    result = engine.score(state.batch, policy)
    has_critical = any("critical" in f for f in result.per_shipment_flags.values())
    needs_review = result.otif_pct < policy.review_threshold_pct or has_critical
    summary = (f"OTIF {result.otif_pct}% grade {result.grade} under policy "
               f"{policy.policy_id}/{policy.version}, "
               f"{len(result.per_shipment_flags)} flagged; needs_review={needs_review}")
    return {"result": result, "needs_review": needs_review,
            "audit_log": state.audit_log + [audit("scoring", summary)]}
