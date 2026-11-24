import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "secret-utilise-uniquement-pour-les-tests")

from fastapi.testclient import TestClient

from app.main import app
from app.security.dependencies import utilisateur_connecte


class TestSuppressionParcelle(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.patch = patch("app.routers.parcelles.get_connection")
        connexion = self.patch.start()
        self.cur = MagicMock()
        connexion.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = self.cur
        app.dependency_overrides[utilisateur_connecte] = lambda: 7
        self.liens = dict.fromkeys(("capteurs", "equipements", "regles", "diagnostics"), False)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.patch.stop()
        self.client.close()

    def supprimer(self):
        return self.client.delete("/api/v1/parcelles/42")

    def test_suppression_exploitant_et_admin(self):
        for role in ("exploitant", "admin"):
            with self.subTest(role=role):
                self.cur.reset_mock()
                self.cur.fetchone.side_effect = [{"role": role}, self.liens]
                reponse = self.supprimer()
                self.assertEqual(reponse.status_code, 204)
                self.assertEqual(reponse.content, b"")
                self.assertEqual(self.cur.execute.call_args_list[0].args[1], (42, 7))
                self.assertIn("FOR UPDATE OF p", self.cur.execute.call_args_list[0].args[0])
                self.assertEqual(self.cur.execute.call_args_list[1].args[1], (42, 42, 42, 42))
                self.assertEqual(self.cur.execute.call_args.args, ("DELETE FROM parcelle WHERE id = %s", (42,)))

    def test_donnees_liees_preservees(self):
        for lien in self.liens:
            with self.subTest(lien=lien):
                self.cur.reset_mock()
                self.cur.fetchone.side_effect = [{"role": "exploitant"}, {**self.liens, lien: True}]
                reponse = self.supprimer()
                self.assertEqual(reponse.status_code, 409)
                self.assertEqual(reponse.headers["content-type"], "application/problem+json")
                self.assertEqual(self.cur.execute.call_count, 2)

    def test_acces_refuse(self):
        for membre, statut in [(None, 404), ({"role": "technicien"}, 403)]:
            with self.subTest(statut=statut):
                self.cur.reset_mock()
                self.cur.fetchone.return_value = membre
                self.assertEqual(self.supprimer().status_code, statut)
                self.assertEqual(self.cur.execute.call_count, 1)

    def test_jwt_requis(self):
        app.dependency_overrides.clear()
        self.assertEqual(self.supprimer().status_code, 401)
        self.cur.execute.assert_not_called()

    def test_identifiant_invalide(self):
        self.assertEqual(self.client.delete("/api/v1/parcelles/0").status_code, 422)
        self.cur.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
