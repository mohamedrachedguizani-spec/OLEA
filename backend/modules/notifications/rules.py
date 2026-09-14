def has_important_reconciliation_discrepancy(
    discrepancies_count: int,
    total_discrepancy_amount: float,
    count_threshold: int = 5,
    amount_threshold: float = 1000.0,
) -> bool:
    """Détermine si un rapprochement doit déclencher une alerte importante."""
    return (
        discrepancies_count >= count_threshold
        or abs(total_discrepancy_amount) >= amount_threshold
    )
