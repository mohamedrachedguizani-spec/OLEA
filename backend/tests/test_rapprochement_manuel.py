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
from modules.rapprochement_bancaire.router import carryover_consumption_keys
from modules.rapprochement_bancaire.models import ReconciliationOptions
from modules.rapprochement_bancaire.service import (
    apply_manual_reconciliations,
    movement_identity,
    reconcile,
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

    def test_manual_pair_consumes_its_originating_carryover(self):
        """Une ligne reportée puis rapprochée manuellement ne doit pas revenir le mois suivant."""
        carried_bank = bank("VIR REPORTE", credit=30000)
        carried_bank.carryover_origin_result_id = 11
        carried_bank.carryover_origin_item_index = 3
        carried_bank.carryover_origin_source_type = "bank"

        carried_sage = sage("SAGE REPORTE", debit=30000)
        carried_sage.carryover_origin_result_id = 11
        carried_sage.carryover_origin_item_index = 5
        carried_sage.carryover_origin_source_type = "sage"

        # Ligne courante (sans origine) : ne doit produire aucune clé de consommation.
        current_bank = bank("VIR DU MOIS", debit=100)
        current_sage = sage("SAGE DU MOIS", credit=100)
        current_bank.carryover_origin_result_id = None
        current_bank.carryover_origin_item_index = None
        current_sage.carryover_origin_result_id = None
        current_sage.carryover_origin_item_index = None

        keys = carryover_consumption_keys(
            [carried_bank, current_bank], [carried_sage, current_sage]
        )

        self.assertEqual(keys, {(11, "bank", 3), (11, "sage", 5)})

    def test_only_the_selected_lines_are_hidden(self):
        bank_movements = [bank("A", debit=100, reference="R1"), bank("B", debit=200, reference="R2")]
        sage_movements = [sage("X", debit=100, piece="P1")]
        result = build_result(bank_movements, sage_movements)

        result.manual_reconciliations.append(ManualReconciliationPair(
            bank=[bank_movements[0]], sage=[sage_movements[0]], bank_total=100.0, sage_total=100.0,
        ))
        apply_manual_reconciliations(result)

        self.assertEqual([item.libelle for item in result.bank_only], ["B"])


class AmountDiscrepancyDetectionTests(unittest.TestCase):
    def test_same_date_different_amounts_stay_separate(self):
        """La détection d'écart est désactivée : les deux lignes restent non rapprochées."""
        options = ReconciliationOptions(date_tolerance_days=3)
        result = reconcile(
            [bank("VIR DUPONT", debit=1000)],
            [sage("VIR DUPONT", debit=900)],
            options,
        )

        self.assertEqual(result.discrepancies, [])
        self.assertEqual(len(result.bank_only), 1)
        self.assertEqual(len(result.sage_only), 1)
        self.assertEqual(result.stats.discrepancies_count, 0)
        self.assertEqual(result.stats.total_discrepancy_amount, 0.0)

    def test_equal_amounts_still_reconcile(self):
        """La désactivation des écarts ne touche pas le rapprochement par montant."""
        options = ReconciliationOptions(date_tolerance_days=3)
        result = reconcile(
            [bank("VIR X", debit=500)],
            [sage("VIR X", debit=500)],
            options,
        )

        self.assertEqual(len(result.reconciled), 1)
        self.assertEqual(result.discrepancies, [])


if __name__ == "__main__":
    unittest.main()