"""Deterministic forecasting math (FR-13) — pure functions, no DB/LLM."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

from app.services.forecasting import (
    forecast_stockout,
    moving_average_daily_demand,
    project_days_until_stockout,
)


def _product(sku="SKU-1", name="Coffee"):
    product = type("P", (), {})()
    product.id = uuid.uuid4()
    product.sku = sku
    product.name = name
    return product


def _inventory(quantity, threshold=10, reorder_qty=50):
    inv = type("I", (), {})()
    inv.quantity_on_hand = quantity
    inv.reorder_threshold = threshold
    inv.reorder_quantity = reorder_qty
    return inv


def test_moving_average_includes_zero_days():
    today = date(2026, 9, 8)
    sales = {today - timedelta(days=1): 7}  # only one day had sales
    # 14-day window: total 7 over 14 days -> 0.5/day
    assert moving_average_daily_demand(sales, window_days=14, today=today) == Decimal("0.5")


def test_moving_average_empty_series_is_zero():
    assert moving_average_daily_demand({}, window_days=14) == Decimal("0")


def test_projection_when_demand_is_zero_never_stockouts():
    assert project_days_until_stockout(100, Decimal("0")) is None


def test_projection_rounds_up():
    # 10 units, 3/day -> ceil(10/3) = 4 days
    assert project_days_until_stockout(10, Decimal("3")) == 4


def test_projection_zero_on_hand_is_immediate():
    assert project_days_until_stockout(0, Decimal("3")) == 0


def test_forecast_stockout_marks_at_risk_when_before_lead_time():
    today = date(2026, 9, 8)
    # 2-day window, 5/day -> out in 2 days; lead time 3 -> at risk.
    row = forecast_stockout(
        _product(), _inventory(10), {today: 5, today - timedelta(days=1): 5}, 3,
        window_days=2, today=today,
    )
    assert row["days_until_stockout"] == 2
    assert row["at_risk"] is True
    assert row["stockout_date"] == (today + timedelta(days=2)).isoformat()


def test_forecast_stockout_safe_when_after_lead_time():
    today = date(2026, 9, 8)
    # 2-day window, 2/day -> out in 50 days; lead time 3 -> safe.
    row = forecast_stockout(
        _product(), _inventory(100), {today: 2, today - timedelta(days=1): 2}, 3,
        window_days=2, today=today,
    )
    assert row["at_risk"] is False
    assert row["days_until_stockout"] == 50


def test_forecast_stockout_no_lead_time_is_not_at_risk():
    # No supplier offer on file -> lead_time None -> can't conclude "before a
    # reorder could arrive", so not flagged at_risk.
    today = date(2026, 9, 8)
    row = forecast_stockout(_product(), _inventory(10), {today: 5}, None, window_days=1, today=today)
    assert row["days_until_stockout"] == 2
    assert row["at_risk"] is False


def test_forecast_stockout_zero_demand_never_runs_out():
    row = forecast_stockout(_product(), _inventory(100), {}, 3)
    assert row["days_until_stockout"] is None
    assert row["stockout_date"] is None
    assert row["at_risk"] is False