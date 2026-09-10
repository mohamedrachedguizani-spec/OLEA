import unittest
from datetime import date
from decimal import Decimal

from modules.sage_bfc.mapper import SageBFCMapper
from modules.sage_bfc.models import LigneComptableSage
from modules.sage_bfc.parser import SageBalanceParser, UnmappedAccountsError


class TestSageBfcUnmappedAccounts(unittest.TestCase):
    def setUp(self):
        self.mapper = SageBFCMapper({
            "mapping_autres_charges": {
                "600001": {
                    "agregat_bfc": "Autres Charges",
                    "categorie": "Charges",
                    "type": "Charge",
                    "sens": "-",
                }
            }
        })
        self.parser = SageBalanceParser(self.mapper)

    @staticmethod
    def line(code, label, debit="0", credit="0"):
        debit_value = Decimal(debit)
        credit_value = Decimal(credit)
        return LigneComptableSage(
            code_compte=code,
            libelle=label,
            debit=debit_value,
            credit=credit_value,
            solde=credit_value - debit_value,
        )

    def test_only_unmapped_class_6_and_7_accounts_are_reported(self):
        accounts = self.parser._find_unmapped_class_6_7_accounts([
            self.line("600001", "Mapped", debit="10"),
            self.line("700001", "Missing product", credit="25"),
            self.line("400001", "Ignored class", credit="50"),
        ])

        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["code_compte"], "700001")
        self.assertEqual(accounts[0]["solde"], Decimal("25"))

    def test_duplicate_accounts_are_grouped_with_amount_details(self):
        accounts = self.parser._find_unmapped_class_6_7_accounts([
            self.line("610000", "Rent", debit="100"),
            self.line("610000", "Rent", credit="30"),
        ])

        self.assertEqual(accounts[0]["nombre_lignes"], 2)
        self.assertEqual(accounts[0]["debit"], Decimal("100"))
        self.assertEqual(accounts[0]["credit"], Decimal("30"))
        self.assertEqual(accounts[0]["solde"], Decimal("-70"))

    def test_parse_is_blocked_before_mapping_when_account_is_missing(self):
        csv_content = b"Code compte;Libelle;Debit;Credit\n700002;Sales;0;120\n"

        with self.assertRaises(UnmappedAccountsError) as context:
            self.parser.parse_file(csv_content, "balance.csv", date(2026, 8, 1))

        self.assertEqual(context.exception.accounts[0]["code_compte"], "700002")
        self.assertEqual(context.exception.total_balance, Decimal("120"))


if __name__ == "__main__":
    unittest.main()
