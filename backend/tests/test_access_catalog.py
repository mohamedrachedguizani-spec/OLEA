import unittest

from modules.access.catalog import PERMISSIONS, PROFILES


class TestAccessCatalog(unittest.TestCase):
    def test_profile_permissions_exist_in_catalog(self):
        for profile_code, (_, _, permission_codes) in PROFILES.items():
            with self.subTest(profile=profile_code):
                self.assertFalse(set(permission_codes) - set(PERMISSIONS))

    def test_super_admin_is_administration_only_by_default(self):
        super_admin_codes = PROFILES["SUPER_ADMIN"][2]
        self.assertTrue(super_admin_codes)
        self.assertTrue(all(code.startswith("admin.") for code in super_admin_codes))

    def test_caisse_mutations_use_one_permission(self):
        manage_code = "saisie_caisse.crud_ecriture_caisse_manage"
        self.assertIn(manage_code, PERMISSIONS)
        self.assertIn(manage_code, PROFILES["COMPTABLE"][2])
        for old_code in (
            "saisie_caisse.create", "saisie_caisse.update",
            "saisie_caisse.delete", "saisie_caisse.migrate",
        ):
            self.assertNotIn(old_code, PERMISSIONS)

    def test_sage_bfc_exposes_only_four_functional_permissions(self):
        sage_bfc_codes = {code for code in PERMISSIONS if code.startswith("sage_bfc.")}
        self.assertEqual(sage_bfc_codes, {
            "sage_bfc.read",
            "sage_bfc.import",
            "sage_bfc.month.delete",
            "sage_bfc.year.close",
        })


if __name__ == "__main__":
    unittest.main()
