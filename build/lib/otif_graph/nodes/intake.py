"""Intake node: LLM parses messy free text into a typed ShipmentBatch.

One retry with the validation error; a second failure routes to escalation.
"""
from pydantic import ValidationError

from otif_graph.state import GraphState, ShipmentBatch, audit

PROMPT = """TASK: parse
Convert the carrier delivery report below into JSON only — no prose, no code
fences — matching this schema exactly:
{{"carrier_name": str, "period": str, "records": [{{"shipment_id": str,
"carrier": str, "promised_date": "YYYY-MM-DD", "delivered_date": "YYYY-MM-DD",
"qty_ordered": int, "qty_delivered": int}}]}}

REPORT:
{raw}{retry_note}"""

RETRY_NOTE = """

Your previous output failed validation with this error:
{error}
Return corrected JSON only."""


def make_intake(llm):
    def intake(state: GraphState) -> dict:
        error = None
        for attempt in (1, 2):
            note = RETRY_NOTE.format(error=error) if error else ""
            raw_out = llm.complete(PROMPT.format(raw=state.raw_request, retry_note=note))
            try:
                batch = ShipmentBatch.model_validate_json(raw_out)
            except ValidationError as exc:
                error = str(exc).splitlines()[0] or "invalid JSON"
                continue
            summary = f"parsed {len(batch.records)} records for {batch.carrier_name} (attempt {attempt})"
            return {"batch": batch, "needs_review": False,
                    "audit_log": state.audit_log + [audit("intake", summary)]}
        return {"batch": None, "needs_review": True,
                "audit_log": state.audit_log + [audit("intake", "parse failed after retry; escalating")]}
    return intake
