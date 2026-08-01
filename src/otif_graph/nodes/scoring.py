"""Scoring node: calls the deterministic engine and nothing else.

This file must never import llm, ollama, requests, langchain, or langgraph.
Enforced by tests/test_no_llm_in_math.py.
"""
from otif_graph import engine
from otif_graph.state import GraphState, audit

REVIEW_THRESHOLD_PCT = 85.0


def scoring(state: GraphState) -> dict:
    result = engine.score(state.batch)
    has_critical = any("critical" in f for f in result.per_shipment_flags.values())
    needs_review = result.otif_pct < REVIEW_THRESHOLD_PCT or has_critical
    summary = (f"OTIF {result.otif_pct}% grade {result.grade}, "
               f"{len(result.per_shipment_flags)} flagged; needs_review={needs_review}")
    return {"result": result, "needs_review": needs_review,
            "audit_log": state.audit_log + [audit("scoring", summary)]}
