import pytest

from app.services.invoicing import format_invoice_number


def test_formats_with_zero_padding():
    assert format_invoice_number(1) == "INV-000001"
    assert format_invoice_number(42) == "INV-000042"


def test_does_not_truncate_large_sequences():
    assert format_invoice_number(1234567) == "INV-1234567"


def test_rejects_non_positive_sequence():
    with pytest.raises(ValueError):
        format_invoice_number(0)
    with pytest.raises(ValueError):
        format_invoice_number(-1)
