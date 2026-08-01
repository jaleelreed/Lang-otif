"""Pins the exact headline outputs for all three fixtures against
fixtures/expected/. Config or logic drift must fail here even if unit tests
pass."""
import json

import pytest

from conftest import EXPECTED, raw_request


@pytest.mark.parametrize("name", ["blue_ridge", "meridian", "cascade"])
def test_headline_pin(graph, name):
    out = graph.invoke({"raw_request": raw_request(name)},
                       config={"configurable": {"thread_id": f"pin-{name}"}})
    expected = json.loads((EXPECTED / f"{name}.json").read_text(encoding="utf-8"))
    result = out["result"]
    assert result.on_time_pct == expected["on_time_pct"]
    assert result.in_full_pct == expected["in_full_pct"]
    assert result.otif_pct == expected["otif_pct"]
    assert result.grade == expected["grade"]
    assert result.per_shipment_flags == expected["per_shipment_flags"]
    critical_count = sum("critical" in f for f in result.per_shipment_flags.values())
    expected_critical = sum("critical" in f for f in expected["per_shipment_flags"].values())
    assert critical_count == expected_critical
