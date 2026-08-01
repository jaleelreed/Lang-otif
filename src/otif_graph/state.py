"""Typed state models for the OTIF graph."""
from __future__ import annotations

from datetime import date, datetime, timezone

from pydantic import BaseModel, Field


class ShipmentRecord(BaseModel):
    shipment_id: str
    carrier: str
    promised_date: date
    delivered_date: date
    qty_ordered: int
    qty_delivered: int


class ShipmentBatch(BaseModel):
    carrier_name: str
    period: str
    records: list[ShipmentRecord]


class OtifResult(BaseModel):
    on_time_pct: float
    in_full_pct: float
    otif_pct: float
    grade: str
    per_shipment_flags: dict[str, list[str]] = Field(default_factory=dict)


class GraphState(BaseModel):
    raw_request: str = ""
    batch: ShipmentBatch | None = None
    result: OtifResult | None = None
    needs_review: bool = False
    review_decision: str | None = None
    narrative: str | None = None
    audit_log: list[str] = Field(default_factory=list)


def audit(node: str, summary: str) -> str:
    """One decision-ledger line: timestamp, node, what happened."""
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return f"{ts} {node}: {summary}"
