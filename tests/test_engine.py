"""Unit coverage of every scoring rule and grade boundary."""
from datetime import date, timedelta

from otif_graph.engine import flags_for, grade_for, score
from otif_graph.state import ShipmentBatch, ShipmentRecord

PROMISED = date(2026, 6, 10)


def rec(sid="S-1", days_late=0, ordered=100, delivered=100):
    return ShipmentRecord(
        shipment_id=sid, carrier="Test", promised_date=PROMISED,
        delivered_date=PROMISED + timedelta(days=days_late),
        qty_ordered=ordered, qty_delivered=delivered)


def batch(records):
    return ShipmentBatch(carrier_name="Test", period="2026-06", records=records)


def batch_with_good_ratio(good, total):
    records = [rec(sid=f"G-{i}") for i in range(good)]
    records += [rec(sid=f"B-{i}", days_late=1) for i in range(total - good)]
    return batch(records)


def test_empty_batch():
    result = score(batch([]))
    assert result.otif_pct == 0.0
    assert result.on_time_pct == 0.0
    assert result.in_full_pct == 0.0
    assert result.grade == "F"
    assert result.per_shipment_flags == {}


def test_same_day_delivery_is_on_time():
    result = score(batch([rec(days_late=0)]))
    assert result.on_time_pct == 100.0


def test_early_delivery_is_on_time():
    result = score(batch([rec(days_late=-3)]))
    assert result.otif_pct == 100.0


def test_one_day_late_fails_on_time():
    result = score(batch([rec(days_late=1)]))
    assert result.on_time_pct == 0.0
    assert result.per_shipment_flags["S-1"] == ["late"]


def test_exact_quantity_is_in_full():
    result = score(batch([rec(ordered=100, delivered=100)]))
    assert result.in_full_pct == 100.0


def test_over_delivery_is_in_full():
    result = score(batch([rec(ordered=100, delivered=110)]))
    assert result.in_full_pct == 100.0


def test_short_delivery_flags():
    result = score(batch([rec(ordered=100, delivered=99)]))
    assert result.in_full_pct == 0.0
    assert "short" in result.per_shipment_flags["S-1"]


def test_otif_requires_both():
    # one late-but-full, one on-time-but-short: 100% of neither combined
    result = score(batch([rec(sid="A", days_late=1), rec(sid="B", delivered=90)]))
    assert result.on_time_pct == 50.0
    assert result.in_full_pct == 50.0
    assert result.otif_pct == 0.0


def test_rounding_one_decimal():
    result = score(batch_with_good_ratio(1, 3))
    assert result.otif_pct == 33.3


def test_grade_boundaries():
    assert grade_for(95.0) == "A"
    assert grade_for(94.9) == "B"
    assert grade_for(90.0) == "B"
    assert grade_for(89.9) == "C"
    assert grade_for(80.0) == "C"
    assert grade_for(79.9) == "D"
    assert grade_for(70.0) == "D"
    assert grade_for(69.9) == "F"
    assert grade_for(0.0) == "F"


def test_grade_boundaries_via_score():
    assert score(batch_with_good_ratio(19, 20)).grade == "A"   # 95.0
    assert score(batch_with_good_ratio(9, 10)).grade == "B"    # 90.0
    assert score(batch_with_good_ratio(8, 10)).grade == "C"    # 80.0
    assert score(batch_with_good_ratio(7, 10)).grade == "D"    # 70.0
    assert score(batch_with_good_ratio(6, 10)).grade == "F"    # 60.0


def test_critical_late_boundary():
    assert "critical" not in flags_for(rec(days_late=7))
    assert "critical" in flags_for(rec(days_late=8))


def test_critical_fill_boundary():
    assert "critical" not in flags_for(rec(ordered=100, delivered=80))  # exactly 80%
    assert "critical" in flags_for(rec(ordered=100, delivered=79))


def test_zero_ordered_quantity_not_critical():
    assert flags_for(rec(ordered=0, delivered=0)) == []
