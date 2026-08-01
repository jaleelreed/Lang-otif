"""Typed state models for the OTIF graph."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

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


class ScoringPolicy(BaseModel):
    """Contract terms as versioned data, not code. A score is only defensible
    if it can be replayed under the exact policy that produced it, so the
    policy id/version are stamped into every result and audit line."""
    policy_id: str = "standard"
    version: str = "v1"
    grade_bands: dict[str, float] = Field(
        default_factory=lambda: {"A": 95.0, "B": 90.0, "C": 80.0, "D": 70.0})
    review_threshold_pct: float = 85.0
    critical_days_late: int = 7
    critical_fill_rate: float = 0.80
    weighting: Literal["shipments", "units"] = "shipments"


class OtifResult(BaseModel):
    on_time_pct: float
    in_full_pct: float
    otif_pct: float
    grade: str
    per_shipment_flags: dict[str, list[str]] = Field(default_factory=dict)
    policy_id: str = "standard"
    policy_version: str = "v1"
    # share of total weight each non-OTIF shipment cost the score, in pct
    miss_drivers: dict[str, float] = Field(default_factory=dict)


class GraphState(BaseModel):
    raw_request: str = ""
    policy: ScoringPolicy | None = None
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
