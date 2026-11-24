import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "secret-utilise-uniquement-pour-les-tests")

from fastapi.testclient import TestClient

from app.main import app
from app.security.dependencies import utilisateur_connecte


class TestModificationParcelle(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.patch = patch("app.routers.parcelles.get_connection")
        connexion = self.patch.start()
        self.cur = MagicMock()
        connexion.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = self.cur
        app.dependency_overrides[utilisateur_connecte] = lambda: 7
        self.parcelle = {"id": 42, "exploitation": 2, "code": "p1", "nom": "Tomates",
                         "culture": "tomate", "surface_m2": 120, "seuil_sec": 25}

    def tearDown(self):
        app.dependency_overrides.clear()
        self.patch.stop()
        self.client.close()

    def modifier(self, donnees):
        return self.client.patch("/api/v1/parcelles/42", json=donnees)

    def test_modification_partielle_selon_role(self):
        for role in ("exploitant", "admin"):
            with self.subTest(role=role):
                self.cur.reset_mock()
                self.cur.fetchone.side_effect = [{"role": role}, {**self.parcelle, "seuil_sec": 30}]
                reponse = self.modifier({"seuil_sec": 30})
                self.assertEqual(reponse.status_code, 200)
                self.assertEqual(reponse.json()["nom"], "Tomates")
                self.assertEqual(reponse.json()["seuil_sec"], 30)
                self.assertEqual(self.cur.execute.call_args_list[0].args[1], (42, 7))
                requete, valeurs = self.cur.execute.call_args.args
                texte = requete.as_string()
                self.assertIn('"seuil_sec" = %s', texte)
                self.assertNotIn('"nom" =', texte)
                self.assertEqual(valeurs, (30, 42))

    def test_surface_effacable(self):
        self.cur.fetchone.side_effect = [{"role": "exploitant"}, {**self.parcelle, "surface_m2": None}]
        reponse = self.modifier({"surface_m2": None})
        self.assertEqual(reponse.status_code, 200)
        self.assertIsNone(reponse.json()["surface_m2"])
        self.assertEqual(self.cur.execute.call_args.args[1], (None, 42))

    def test_acces_refuse_sans_ecriture(self):
        for membre, statut in [(None, 404), ({"role": "technicien"}, 403)]:
            with self.subTest(statut=statut):
                self.cur.reset_mock()
                self.cur.fetchone.return_value = membre
                reponse = self.modifier({"nom": "Nouveau nom"})
                self.assertEqual(reponse.status_code, statut)
                self.assertEqual(self.cur.execute.call_count, 1)

    def test_validation_sans_ecriture(self):
        for donnees in [{}, {"code": "p2"}, {"exploitation": 3}, {"nom": None},
                        {"nom": "   "}, {"culture": None}, {"seuil_sec": None},
                        {"seuil_sec": -1}, {"surface_m2": 0}, {"surface_m2": 1.234}]:
            with self.subTest(donnees=donnees):
                reponse = self.modifier(donnees)
                self.assertEqual(reponse.status_code, 422)
                self.assertEqual(reponse.headers["content-type"], "application/problem+json")
        self.cur.execute.assert_not_called()

    def test_jwt_requis(self):
        app.dependency_overrides.clear()
        self.assertEqual(self.modifier({"nom": "Nouveau nom"}).status_code, 401)
        self.cur.execute.assert_not_called()

    def test_identifiant_invalide(self):
        reponse = self.client.patch("/api/v1/parcelles/0", json={"nom": "Nouveau nom"})
        self.assertEqual(reponse.status_code, 422)
        self.cur.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
