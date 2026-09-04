def format_invoice_number(sequence: int) -> str:
    """sequence is 1-based (the Nth invoice for the business). Known race
    condition under concurrent order creation for the same business — see
    docs/decisions.md ADR-014.
    """
    if sequence < 1:
        raise ValueError("sequence must be >= 1")
    return f"INV-{sequence:06d}"
