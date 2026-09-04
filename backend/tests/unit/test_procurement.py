import uuid
from decimal import Decimal

from app.schemas.supplier import SupplierPriceComparisonRow
from app.services.procurement import rank_supplier_offers


def _offer(name: str, price: str, lead_time: int, is_active: bool = True) -> SupplierPriceComparisonRow:
    return SupplierPriceComparisonRow(
        supplier_id=uuid.uuid4(),
        supplier_name=name,
        is_active=is_active,
        price=Decimal(price),
        lead_time_days=lead_time,
    )


def test_ranks_by_price_ascending():
    offers = [_offer("B", "20.00", 3), _offer("A", "10.00", 5)]
    ranked = rank_supplier_offers(offers)
    assert [o.supplier_name for o in ranked] == ["A", "B"]


def test_active_suppliers_rank_before_inactive_regardless_of_price():
    offers = [
        _offer("Cheap-but-inactive", "5.00", 1, is_active=False),
        _offer("Active", "50.00", 1, is_active=True),
    ]
    ranked = rank_supplier_offers(offers)
    assert ranked[0].supplier_name == "Active"


def test_ties_on_price_broken_by_lead_time():
    offers = [
        _offer("Slow", "10.00", 10),
        _offer("Fast", "10.00", 2),
    ]
    ranked = rank_supplier_offers(offers)
    assert [o.supplier_name for o in ranked] == ["Fast", "Slow"]
