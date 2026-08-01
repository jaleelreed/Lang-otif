"""LLM interface. FakeLLM (default) is deterministic and offline; OllamaLLM is
an optional free local model. Nothing here requires an API key.
"""
import json
import urllib.error
import urllib.request
from typing import Protocol

OLLAMA_HELP = """\
No Ollama server reachable. To use --local (free, no API key):
  1. Install Ollama: https://ollama.com/download
  2. Pull a model:   ollama pull llama3.1:8b
  3. Start it:       ollama serve   (usually starts automatically)
Then re-run with --local. Everything else in this repo works without it
via the deterministic FakeLLM."""


class LLM(Protocol):
    def complete(self, prompt: str) -> str: ...


# ---------------------------------------------------------------------------
# FakeLLM: canned parses/narratives keyed to the bundled fixtures.

_BLUE_RIDGE = {
    "carrier_name": "Blue Ridge Logistics", "period": "2026-06",
    "records": [
        {"shipment_id": "BR-101", "carrier": "Blue Ridge Logistics", "promised_date": "2026-06-03", "delivered_date": "2026-06-02", "qty_ordered": 500, "qty_delivered": 500},
        {"shipment_id": "BR-102", "carrier": "Blue Ridge Logistics", "promised_date": "2026-06-07", "delivered_date": "2026-06-07", "qty_ordered": 240, "qty_delivered": 240},
        {"shipment_id": "BR-103", "carrier": "Blue Ridge Logistics", "promised_date": "2026-06-12", "delivered_date": "2026-06-10", "qty_ordered": 1200, "qty_delivered": 1200},
        {"shipment_id": "BR-104", "carrier": "Blue Ridge Logistics", "promised_date": "2026-06-18", "delivered_date": "2026-06-18", "qty_ordered": 80, "qty_delivered": 80},
        {"shipment_id": "BR-105", "carrier": "Blue Ridge Logistics", "promised_date": "2026-06-25", "delivered_date": "2026-06-24", "qty_ordered": 640, "qty_delivered": 640},
    ],
}

_MERIDIAN = {
    "carrier_name": "Meridian Freight", "period": "2026-06",
    "records": [
        {"shipment_id": "M-001", "carrier": "Meridian Freight", "promised_date": "2026-06-04", "delivered_date": "2026-06-04", "qty_ordered": 300, "qty_delivered": 300},
        {"shipment_id": "M-002", "carrier": "Meridian Freight", "promised_date": "2026-06-06", "delivered_date": "2026-06-16", "qty_ordered": 450, "qty_delivered": 450},
        {"shipment_id": "M-003", "carrier": "Meridian Freight", "promised_date": "2026-06-10", "delivered_date": "2026-06-09", "qty_ordered": 800, "qty_delivered": 400},
        {"shipment_id": "M-004", "carrier": "Meridian Freight", "promised_date": "2026-06-15", "delivered_date": "2026-06-17", "qty_ordered": 120, "qty_delivered": 120},
        {"shipment_id": "M-005", "carrier": "Meridian Freight", "promised_date": "2026-06-20", "delivered_date": "2026-06-19", "qty_ordered": 950, "qty_delivered": 950},
        {"shipment_id": "M-006", "carrier": "Meridian Freight", "promised_date": "2026-06-26", "delivered_date": "2026-06-26", "qty_ordered": 200, "qty_delivered": 180},
    ],
}

_CASCADE = {
    "carrier_name": "Cascade Carriers", "period": "2026-07",
    "records": [
        {"shipment_id": "C-101", "carrier": "Cascade Carriers", "promised_date": "2026-07-02", "delivered_date": "2026-07-01", "qty_ordered": 150, "qty_delivered": 150},
        {"shipment_id": "C-102", "carrier": "Cascade Carriers", "promised_date": "2026-07-05", "delivered_date": "2026-07-05", "qty_ordered": 320, "qty_delivered": 320},
        {"shipment_id": "C-103", "carrier": "Cascade Carriers", "promised_date": "2026-07-09", "delivered_date": "2026-07-08", "qty_ordered": 75, "qty_delivered": 75},
        {"shipment_id": "C-104", "carrier": "Cascade Carriers", "promised_date": "2026-07-11", "delivered_date": "2026-07-12", "qty_ordered": 400, "qty_delivered": 400},
        {"shipment_id": "C-105", "carrier": "Cascade Carriers", "promised_date": "2026-07-16", "delivered_date": "2026-07-15", "qty_ordered": 260, "qty_delivered": 260},
        {"shipment_id": "C-106", "carrier": "Cascade Carriers", "promised_date": "2026-07-20", "delivered_date": "2026-07-20", "qty_ordered": 90, "qty_delivered": 90},
        {"shipment_id": "C-107", "carrier": "Cascade Carriers", "promised_date": "2026-07-24", "delivered_date": "2026-07-22", "qty_ordered": 510, "qty_delivered": 510},
        {"shipment_id": "C-108", "carrier": "Cascade Carriers", "promised_date": "2026-07-29", "delivered_date": "2026-07-29", "qty_ordered": 880, "qty_delivered": 880},
    ],
}

_NARRATIVES = {
    "Blue Ridge Logistics": (
        "Blue Ridge Logistics closed the period with a flawless scorecard. Every "
        "shipment arrived on schedule (100.0% on time) and complete (100.0% in "
        "full), producing an OTIF of 100.0% and a grade of A. No shipments were "
        "flagged. This is the service level to hold the carrier to at the next "
        "review; no corrective action is needed."
    ),
    "Meridian Freight": (
        "Meridian Freight fell well short this period. Only 66.7% of shipments "
        "arrived on time and 66.7% arrived in full, and OTIF landed at 33.3% for "
        "a grade of F. Two shipments were critically flagged — one severely late "
        "and one roughly half-filled — and a reviewer has signed off on the "
        "escalation. Recommend a corrective-action request before the next "
        "planning cycle."
    ),
    "Cascade Carriers": (
        "Cascade Carriers turned in a solid month despite a garbled report that "
        "took a second parsing pass. On-time performance was 87.5%, fill was "
        "perfect at 100.0%, and OTIF landed at 87.5% for a grade of C. One "
        "shipment was flagged for a minor delay; nothing was critical. Worth "
        "watching, not worth escalating."
    ),
}


class FakeLLM:
    """Deterministic canned outputs keyed to the fixtures. No network, no keys.

    The Cascade fixture deliberately returns broken JSON on the first parse
    attempt to exercise the intake retry path; the retry prompt (which carries
    the validation error) gets the corrected output.
    """

    def complete(self, prompt: str) -> str:
        if prompt.startswith("TASK: narrate"):
            for carrier, text in _NARRATIVES.items():
                if carrier in prompt:
                    return text
            return "No canned narrative for this input."
        # TASK: parse
        if "Blue Ridge" in prompt:
            return json.dumps(_BLUE_RIDGE)
        if "Meridian" in prompt:
            return json.dumps(_MERIDIAN)
        if "Cascade" in prompt or "CASCADE" in prompt:
            if "failed validation" in prompt:
                return json.dumps(_CASCADE)
            return json.dumps({"carrier_name": "Cascade Carriers",
                               "period": "2026-07", "records": "SEE ATTACHED"})
        return "I cannot parse this."


class OllamaLLM:
    """Free local model via Ollama's HTTP API. Optional; never required."""

    def __init__(self, model: str = "llama3.1:8b",
                 base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def complete(self, prompt: str) -> str:
        body = json.dumps({"model": self.model, "prompt": prompt,
                           "stream": False}).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/generate", data=body,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                return json.loads(resp.read())["response"]
        except (urllib.error.URLError, OSError) as exc:
            raise RuntimeError(OLLAMA_HELP) from exc


def ollama_reachable(base_url: str = "http://localhost:11434") -> bool:
    try:
        urllib.request.urlopen(f"{base_url.rstrip('/')}/api/tags", timeout=3)
        return True
    except (urllib.error.URLError, OSError):
        return False
