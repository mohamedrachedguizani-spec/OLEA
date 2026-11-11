"""Validation des données de création / modification d'un utilisateur.

Ces règles évitent les 422 difficiles à comprendre côté interface :
  - espaces parasites dans l'identifiant, l'email ou le nom complet
  - majuscules (l'identifiant et l'email sont normalisés en minuscules)
  - longueurs supérieures aux colonnes MySQL (500 « Data too long »)
"""

import unittest

from pydantic import ValidationError

from modules.auth.models import UserCreate, UserUpdate


def _payload(**overrides):
    base = {
        "username": "m.diallo",
        "email": "m.diallo@olea.com",
        "full_name": "Mohamed Diallo",
        "password": "Olea123!x",
        "role": "comptable",
    }
    base.update(overrides)
    return base


class TestUserCreateValidation(unittest.TestCase):
    def test_nominal_payload_is_normalized(self):
        user = UserCreate(**_payload(
            username=" M.Diallo ", email=" M.Diallo@OLEA.com ",
            full_name="  Mohamed   Diallo  ",
        ))
        self.assertEqual(user.username, "m.diallo")
        self.assertEqual(user.email, "m.diallo@olea.com")
        self.assertEqual(user.full_name, "Mohamed Diallo")

    def test_ressources_humaines_role_is_accepted(self):
        user = UserCreate(**_payload(role="ressources_humaines"))
        self.assertEqual(user.role.value, "ressources_humaines")

    def test_username_rejects_inner_space_and_accents(self):
        for username in ("Mohamed Diallo", "rené.diallo"):
            with self.subTest(username=username):
                with self.assertRaises(ValidationError):
                    UserCreate(**_payload(username=username))

    def test_email_requires_a_domain_extension(self):
        for email in ("m.diallo@olea", "m.diallo@oléa.com"):
            with self.subTest(email=email):
                with self.assertRaises(ValidationError):
                    UserCreate(**_payload(email=email))

    def test_email_accepts_subdomains(self):
        user = UserCreate(**_payload(email="m.diallo@fin.olea.com"))
        self.assertEqual(user.email, "m.diallo@fin.olea.com")

    def test_full_name_cannot_be_blank(self):
        with self.assertRaises(ValidationError):
            UserCreate(**_payload(full_name="   "))

    def test_lengths_match_database_columns(self):
        with self.assertRaises(ValidationError):
            UserCreate(**_payload(username="a" * 51))
        with self.assertRaises(ValidationError):
            UserCreate(**_payload(full_name="A" * 101))
        with self.assertRaises(ValidationError):
            UserCreate(**_payload(email="a@" + "b" * 96 + ".com"))  # 102 caractères > 100

    def test_password_policy_is_enforced(self):
        for password in ("Olea1234", "Olea123!x ", "olea123!x"):
            with self.subTest(password=password):
                with self.assertRaises(ValidationError):
                    UserCreate(**_payload(password=password))


class TestUserUpdateValidation(unittest.TestCase):
    def test_partial_update_is_normalized(self):
        update = UserUpdate(email=" A.B@OLEA.com ", full_name="  Ali   Ben ")
        self.assertEqual(update.email, "a.b@olea.com")
        self.assertEqual(update.full_name, "Ali Ben")
        self.assertIsNone(update.role)

    def test_partial_update_rejects_invalid_values(self):
        with self.assertRaises(ValidationError):
            UserUpdate(email="a.b@olea")
        with self.assertRaises(ValidationError):
            UserUpdate(full_name="   ")


if __name__ == "__main__":
    unittest.main()
