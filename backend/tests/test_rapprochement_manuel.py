import unittest
from datetime import date, datetime

from modules.rapprochement_bancaire.models import (
    BankMovement,
    ManualReconciliationPair,
    OpeningBalanceInfo,
    ReconciliationContext,
    ReconciliationResult,
    ReconciliationStats,
    SageMovement,
)
from modules.rapprochement_bancaire.service import (
    apply_manual_reconciliations,
    movement_identity,
)


def bank(label, debit=0.0, credit=0.0, reference=None, day=10):
    return BankMovement(
        date_operation=date(2026, 5, day),
        reference=reference,
        libelle=label,
        debit=debit,
        credit=credit,
        amount=debit - credit,
    )


def sage(label, debit=0.0, credit=0.0, piece="P1"):
    return SageMovement(
        code_compte="5320002T",
        libelle_compte="BANQUE",
        date_ecriture=date(2026, 5, 12),
        journal="BI3",
        numero_piece=piece,
        libelle_ecriture=label,
        debit=debit,
        credit=credit,
        amount=debit - credit,
    )


def build_result(bank_only, sage_only):
    stats = ReconciliationStats(
        total_bank_movements=len(bank_only),
        total_sage_movements=len(sage_only),
        auto_reconciled_count=0,
        manual_validation_count=0,
        discrepancies_count=0,
        total_discrepancy_amount=0.0,
        automation_rate=0.0,
        bank_total_debit=sum(item.debit for item in bank_only),
        bank_total_credit=sum(item.credit for item in bank_only),
        sage_total_debit=sum(item.debit for item in sage_only),
        sage_total_credit=sum(item.credit for item in sage_only),
    )
    context = ReconciliationContext(
        bank_journal="BI3",
        account_code="5320002T",
        period="2026-05",
        period_start=date(2026, 5, 1),
        period_end=date(2026, 5, 31),
        sage_opening=OpeningBalanceInfo(amount=1000.0),
        bank_opening=OpeningBalanceInfo(amount=900.0),
        opening_status="conforme",
    )
    return ReconciliationResult(
        stats=stats,
        reconciled=[],
        bank_only=list(bank_only),
        sage_only=list(sage_only),
        discrepancies=[],
        context=context,
    )


class ManualReconciliationTests(unittest.TestCase):
    def test_one_sage_entry_against_three_bank_movements(self):
        """1 écriture Sage de 30 000 face à 3 mouvements banque de 10 000."""
        bank_movements = [
            bank("VIR A", debit=10000, reference="B1"),
            bank("VIR B", debit=10000, reference="B2"),
            bank("VIR C", debit=10000, reference="B3"),
            bank("AUTRE", credit=500, reference="B4"),
        ]
        sage_movements = [
            sage("TOTAL VIR", debit=30000, piece="S1"),
            sage("AUTRE SAGE", credit=500, piece="S2"),
        ]
        result = build_result(bank_movements, sage_movements)

        result.manual_reconciliations.append(ManualReconciliationPair(
            bank=bank_movements[:3],
            sage=sage_movements[:1],
            bank_total=30000.0,
            sage_total=30000.0,
            validated_at=datetime(2026, 5, 20, 10, 0),
            validated_by="comptable",
        ))
        apply_manual_reconciliations(result)

        self.assertEqual(len(result.bank_only), 1)
        self.assertEqual(len(result.sage_only), 1)
        self.assertEqual(result.bank_only[0].libelle, "AUTRE")
        self.assertEqual(result.sage_only[0].libelle_ecriture, "AUTRE SAGE")

    def test_balances_are_recomputed_from_opening(self):
        bank_movements = [bank("VIR A", debit=10000, reference="B1"), bank("AUTRE", credit=500, reference="B4")]
        sage_movements = [sage("TOTAL", debit=10000), sage("AUTRE", credit=500, piece="S2")]
        result = build_result(bank_movements, sage_movements)

        result.manual_reconciliations.append(ManualReconciliationPair(
            bank=bank_movements[:1], sage=sage_movements[:1], bank_total=10000.0, sage_total=10000.0,
        ))
        apply_manual_reconciliations(result)

        context = result.context
        # Les soldes de clôture restent calculés sur les totaux importés.
        self.assertAlmostEqual(context.sage_closing_balance, 10500.0, places=3)
        self.assertAlmostEqual(context.bank_closing_balance, -8600.0, places=3)
        # Seules les lignes restantes ajustent les soldes : « AUTRE » (crédit 500) de chaque côté.
        self.assertAlmostEqual(context.adjusted_sage_balance, 10500.0 - 500.0, places=3)
        self.assertAlmostEqual(context.adjusted_bank_balance, -8600.0 - 500.0, places=3)
        self.assertAlmostEqual(
            context.residual_difference,
            context.adjusted_sage_balance - context.adjusted_bank_balance,
            places=3,
        )

    def test_balances_fall_back_to_closing_when_nothing_is_left_over(self):
        bank_movements = [bank("VIR A", debit=10000, reference="B1")]
        sage_movements = [sage("TOTAL", debit=10000)]
        result = build_result(bank_movements, sage_movements)

        result.manual_reconciliations.append(ManualReconciliationPair(
            bank=bank_movements, sage=sage_movements, bank_total=10000.0, sage_total=10000.0,
        ))
        apply_manual_reconciliations(result)

        context = result.context
        self.assertEqual(result.bank_only, [])
        self.assertEqual(result.sage_only, [])
        self.assertAlmostEqual(context.adjusted_sage_balance, context.sage_closing_balance, places=3)
        self.assertAlmostEqual(context.adjusted_bank_balance, context.bank_closing_balance, places=3)

    def test_application_is_idempotent(self):
        bank_movements = [bank("VIR A", debit=10000, reference="B1")]
        sage_movements = [sage("TOTAL", debit=10000)]
        result = build_result(bank_movements, sage_movements)
        result.manual_reconciliations.append(ManualReconciliationPair(
            bank=bank_movements, sage=sage_movements, bank_total=10000.0, sage_total=10000.0,
        ))

        apply_manual_reconciliations(result)
        apply_manual_reconciliations(result)

        self.assertEqual(result.bank_only, [])
        self.assertEqual(result.sage_only, [])

    def test_identical_movements_have_distinct_identities_when_dated_differently(self):
        first = bank("VIR", debit=100, reference="R1", day=10)
        second = bank("VIR", debit=100, reference="R1", day=11)
        self.assertNotEqual(movement_identity(first), movement_identity(second))

    def test_only_the_selected_lines_are_hidden(self):
        bank_movements = [bank("A", debit=100, reference="R1"), bank("B", debit=200, reference="R2")]
        sage_movements = [sage("X", debit=100, piece="P1")]
        result = build_result(bank_movements, sage_movements)

        result.manual_reconciliations.append(ManualReconciliationPair(
            bank=[bank_movements[0]], sage=[sage_movements[0]], bank_total=100.0, sage_total=100.0,
        ))
        apply_manual_reconciliations(result)

        self.assertEqual([item.libelle for item in result.bank_only], ["B"])


if __name__ == "__main__":
    unittest.main()
