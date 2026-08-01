"""Deterministic OTIF scoring engine.

Pure functions, no I/O. This file must never import llm, ollama, requests,
langchain, or langgraph — no LLM in any code path that produces a number.
Enforced by tests/test_no_llm_in_math.py.

Contract terms (grade bands, tolerances, weighting) come in as a versioned
ScoringPolicy so a past score stays reproducible after a renegotiation.
"""
from otif_graph.state import OtifResult, ScoringPolicy, ShipmentBatch, ShipmentRecord

DEFAULT_POLICY = ScoringPolicy()


def is_on_time(r: ShipmentRecord) -> bool:
    return r.delivered_date <= r.promised_date


def is_in_full(r: ShipmentRecord) -> bool:
    return r.qty_delivered >= r.qty_ordered


def flags_for(r: ShipmentRecord, policy: ScoringPolicy = DEFAULT_POLICY) -> list[str]:
    flags = []
    if not is_on_time(r):
        flags.append("late")
    if not is_in_full(r):
        flags.append("short")
    days_late = (r.delivered_date - r.promised_date).days
    fill = r.qty_delivered / r.qty_ordered if r.qty_ordered else 1.0
    if days_late > policy.critical_days_late or fill < policy.critical_fill_rate:
        flags.append("critical")
    return flags


def grade_for(otif_pct: float, policy: ScoringPolicy = DEFAULT_POLICY) -> str:
    for grade in ("A", "B", "C", "D"):
        if otif_pct >= policy.grade_bands[grade]:
            return grade
    return "F"


def score(batch: ShipmentBatch, policy: ScoringPolicy = DEFAULT_POLICY) -> OtifResult:
    def weight(r: ShipmentRecord) -> float:
        return float(r.qty_ordered) if policy.weighting == "units" else 1.0

    total = sum(weight(r) for r in batch.records)
    if total == 0:
        return OtifResult(on_time_pct=0.0, in_full_pct=0.0, otif_pct=0.0,
                          grade="F", per_shipment_flags={},
                          policy_id=policy.policy_id, policy_version=policy.version)

    def pct(w: float) -> float:
        return round(100.0 * w / total, 1)

    on_time = sum(weight(r) for r in batch.records if is_on_time(r))
    in_full = sum(weight(r) for r in batch.records if is_in_full(r))
    both = sum(weight(r) for r in batch.records if is_on_time(r) and is_in_full(r))
    otif_pct = pct(both)
    flags = {r.shipment_id: f for r in batch.records if (f := flags_for(r, policy))}
    drivers = {r.shipment_id: pct(weight(r)) for r in batch.records
               if not (is_on_time(r) and is_in_full(r))}
    return OtifResult(on_time_pct=pct(on_time), in_full_pct=pct(in_full),
                      otif_pct=otif_pct, grade=grade_for(otif_pct, policy),
                      per_shipment_flags=flags, policy_id=policy.policy_id,
                      policy_version=policy.version, miss_drivers=drivers)
