"""Deterministic OTIF scoring engine.

Pure functions, no I/O. This file must never import llm, ollama, requests,
langchain, or langgraph — no LLM in any code path that produces a number.
Enforced by tests/test_no_llm_in_math.py.
"""
from otif_graph.state import OtifResult, ShipmentBatch, ShipmentRecord

CRITICAL_DAYS_LATE = 7
CRITICAL_FILL_RATE = 0.80


def is_on_time(r: ShipmentRecord) -> bool:
    return r.delivered_date <= r.promised_date


def is_in_full(r: ShipmentRecord) -> bool:
    return r.qty_delivered >= r.qty_ordered


def flags_for(r: ShipmentRecord) -> list[str]:
    flags = []
    if not is_on_time(r):
        flags.append("late")
    if not is_in_full(r):
        flags.append("short")
    days_late = (r.delivered_date - r.promised_date).days
    fill = r.qty_delivered / r.qty_ordered if r.qty_ordered else 1.0
    if days_late > CRITICAL_DAYS_LATE or fill < CRITICAL_FILL_RATE:
        flags.append("critical")
    return flags


def grade_for(otif_pct: float) -> str:
    if otif_pct >= 95:
        return "A"
    if otif_pct >= 90:
        return "B"
    if otif_pct >= 80:
        return "C"
    if otif_pct >= 70:
        return "D"
    return "F"


def score(batch: ShipmentBatch) -> OtifResult:
    n = len(batch.records)
    if n == 0:
        return OtifResult(on_time_pct=0.0, in_full_pct=0.0, otif_pct=0.0,
                          grade="F", per_shipment_flags={})

    def pct(k: int) -> float:
        return round(100.0 * k / n, 1)

    on_time = sum(is_on_time(r) for r in batch.records)
    in_full = sum(is_in_full(r) for r in batch.records)
    both = sum(is_on_time(r) and is_in_full(r) for r in batch.records)
    otif_pct = pct(both)
    flags = {r.shipment_id: f for r in batch.records if (f := flags_for(r))}
    return OtifResult(on_time_pct=pct(on_time), in_full_pct=pct(in_full),
                      otif_pct=otif_pct, grade=grade_for(otif_pct),
                      per_shipment_flags=flags)
