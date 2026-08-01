"""Escalation node: human-in-the-loop interrupt.

Pauses the graph with the score and critical flags; resume with
approve | reject | rescore.
"""
from langgraph.types import interrupt

from otif_graph.state import GraphState, audit

RESCORE_NOTE = "\n[reviewer note: figures disputed — re-parse and rescore]"


def escalation(state: GraphState) -> dict:
    if state.result is None:
        payload = {"score": None, "critical_flags": {},
                   "proposed_action": "Request could not be parsed; approve to close, rescore to retry"}
    else:
        criticals = {sid: f for sid, f in state.result.per_shipment_flags.items()
                     if "critical" in f}
        payload = {"score": state.result.model_dump(),
                   "critical_flags": criticals,
                   "miss_drivers": state.result.miss_drivers,
                   "proposed_action": ("Open a corrective-action claim against the carrier"
                                       if criticals
                                       else "Score is below the contract review threshold — "
                                            "confirm before publishing")}
    decision = interrupt(payload)
    if decision not in ("approve", "reject", "rescore"):
        raise ValueError(f"decision must be approve|reject|rescore, got {decision!r}")
    updates = {"review_decision": decision,
               "audit_log": state.audit_log + [audit("escalation", f"human decision: {decision}")]}
    if decision == "rescore":
        updates.update(raw_request=state.raw_request + RESCORE_NOTE,
                       batch=None, result=None, needs_review=False)
    return updates
