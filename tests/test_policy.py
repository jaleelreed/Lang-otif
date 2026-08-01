"""Per-customer policy versioning: rules are data, results are stamped with
the policy that produced them, and a stricter contract flips outcomes on the
same underlying data."""
import json

from conftest import EXPECTED, POLICIES, node_order, raw_request
from otif_graph.engine import score
from otif_graph.llm import _CASCADE
from otif_graph.state import ScoringPolicy, ShipmentBatch

BIGBOX = ScoringPolicy.model_validate_json(
    (POLICIES / "bigbox-retail.json").read_text(encoding="utf-8"))
CASCADE_BATCH = ShipmentBatch.model_validate(_CASCADE)


def test_result_is_stamped_with_policy():
    result = score(CASCADE_BATCH)
    assert (result.policy_id, result.policy_version) == ("standard", "v1")
    strict = score(CASCADE_BATCH, BIGBOX)
    assert (strict.policy_id, strict.policy_version) == ("bigbox-retail", "2026-Q3")


def test_unit_weighting_changes_the_score():
    # same data: 87.5% by shipment count, 85.1% weighted by units because the
    # one late shipment (C-104, 400 units) carries more weight
    assert score(CASCADE_BATCH).otif_pct == 87.5
    assert score(CASCADE_BATCH, BIGBOX).otif_pct == 85.1


def test_miss_drivers_show_contribution():
    strict = score(CASCADE_BATCH, BIGBOX)
    assert strict.miss_drivers == {"C-104": 14.9}  # 400 of 2685 units


def test_bigbox_pin():
    result = score(CASCADE_BATCH, BIGBOX)
    expected = json.loads((EXPECTED / "cascade_bigbox.json").read_text(encoding="utf-8"))
    assert result.model_dump() == expected


def test_policy_flows_through_graph_and_flips_routing(graph):
    """cascade passes clean under the standard policy but must escalate under
    bigbox-retail (85.1 < 95 threshold); the audit log names the policy."""
    out = graph.invoke(
        {"raw_request": raw_request("cascade"), "policy": BIGBOX},
        config={"configurable": {"thread_id": "t-policy"}})
    assert "__interrupt__" in out
    assert node_order(out["audit_log"]) == ["intake", "scoring"]
    assert "policy bigbox-retail/2026-Q3" in out["audit_log"][1]
    payload = out["__interrupt__"][0].value
    assert payload["miss_drivers"] == {"C-104": 14.9}
