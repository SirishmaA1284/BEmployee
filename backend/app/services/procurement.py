from app.schemas.supplier import SupplierPriceComparisonRow


def rank_supplier_offers(
    offers: list[SupplierPriceComparisonRow],
) -> list[SupplierPriceComparisonRow]:
    """Deterministic supplier ranking: active suppliers before inactive,
    then lowest price, then shortest lead time. Used by both the
    /api/suppliers/compare endpoint and (Phase 4) the Procurement Agent, so
    the AI's supplier recommendation is provably the same ranking a human
    looking at this endpoint would see — not a separate LLM judgment call.
    """
    return sorted(offers, key=lambda offer: (not offer.is_active, offer.price, offer.lead_time_days))
