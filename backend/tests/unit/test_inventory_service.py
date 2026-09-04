from app.services.inventory_service import is_low_stock, is_stock_sufficient


def test_stock_sufficient_when_enough_on_hand():
    assert is_stock_sufficient(quantity_on_hand=10, requested_quantity=5) is True


def test_stock_sufficient_at_exact_boundary():
    assert is_stock_sufficient(quantity_on_hand=5, requested_quantity=5) is True


def test_stock_insufficient_when_not_enough_on_hand():
    assert is_stock_sufficient(quantity_on_hand=3, requested_quantity=5) is False


def test_low_stock_when_at_or_below_threshold():
    assert is_low_stock(quantity_on_hand=5, reorder_threshold=5) is True
    assert is_low_stock(quantity_on_hand=2, reorder_threshold=5) is True


def test_not_low_stock_when_above_threshold():
    assert is_low_stock(quantity_on_hand=10, reorder_threshold=5) is False
