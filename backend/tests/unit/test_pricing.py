from decimal import Decimal

from app.services.pricing import compute_tax, line_total, sum_amounts


def test_line_total_multiplies_quantity_and_price():
    assert line_total(3, Decimal("49.50")) == Decimal("148.50")


def test_line_total_rounds_to_two_decimal_places():
    assert line_total(3, Decimal("10.005")) == Decimal("30.02")


def test_sum_amounts_adds_and_rounds():
    assert sum_amounts([Decimal("10.10"), Decimal("5.05"), Decimal("0.001")]) == Decimal("15.15")


def test_sum_amounts_empty_list_is_zero():
    assert sum_amounts([]) == Decimal("0.00")


def test_compute_tax_is_zero_for_mvp():
    # See docs/decisions.md ADR-014 — no tax engine in MVP.
    assert compute_tax(Decimal("1000.00")) == Decimal("0.00")
