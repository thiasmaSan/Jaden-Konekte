"""Tests sans base réelle, exécutables avec unittest ou pytest."""
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "secret-utilise-uniquement-pour-les-tests")

from fastapi.testclient import TestClient
from psycopg.errors import UniqueViolation

from app.main import app
from app.security.dependencies import utilisateur_connecte


class TestCreationParcelle(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.patch = patch("app.routers.parcelles.get_connection")
        connexion = self.patch.start()
        self.cur = MagicMock()
        connexion.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = self.cur
        app.dependency_overrides[utilisateur_connecte] = lambda: 7
        self.donnees = {"exploitation": 2, "code": "p1", "nom": "Tomates", "culture": "tomate"}

    def tearDown(self):
        app.dependency_overrides.clear()
        self.patch.stop()
        self.client.close()

    def poster(self):
        return self.client.post("/api/v1/parcelles", json=self.donnees)

    def test_creation_exploitant_et_admin(self):
        for role in ("exploitant", "admin"):
            with self.subTest(role=role):
                self.cur.reset_mock()
                self.cur.fetchone.side_effect = [
                    {"role": role}, {"id": 42, **self.donnees, "surface_m2": None, "seuil_sec": 25},
                ]
                reponse = self.poster()
                self.assertEqual(reponse.status_code, 201)
                self.assertEqual(reponse.headers["location"], "/api/v1/parcelles/42")
                self.assertEqual(reponse.json()["seuil_sec"], 25)
                self.assertEqual(self.cur.execute.call_args_list[0].args[1], (7, 2))
                self.assertEqual(self.cur.execute.call_args_list[1].args[1][0], 2)

    def test_technicien_refuse(self):
        self.cur.fetchone.return_value = {"role": "technicien"}
        self.assertEqual(self.poster().status_code, 403)
        self.assertEqual(self.cur.execute.call_count, 1)

    def test_autre_exploitation_inaccessible(self):
        self.cur.fetchone.return_value = None
        self.assertEqual(self.poster().status_code, 404)
        self.assertEqual(self.cur.execute.call_count, 1)

    def test_code_deja_utilise(self):
        self.cur.fetchone.return_value = {"role": "exploitant"}
        self.cur.execute.side_effect = [None, UniqueViolation()]
        reponse = self.poster()
        self.assertEqual(reponse.status_code, 409)
        self.assertEqual(reponse.headers["content-type"], "application/problem+json")

    def test_jwt_requis(self):
        app.dependency_overrides.clear()
        self.assertEqual(self.poster().status_code, 401)
        self.cur.execute.assert_not_called()

    def test_donnees_invalides(self):
        for champ, valeur in [("code", "p/1"), ("nom", "   "), ("exploitation", 0),
                              ("surface_m2", -1), ("surface_m2", 1.234),
                              ("seuil_sec", 101), ("seuil_sec", None), ("inconnu", True)]:
            with self.subTest(champ=champ, valeur=valeur):
                reponse = self.client.post("/api/v1/parcelles", json={**self.donnees, champ: valeur})
                self.assertEqual(reponse.status_code, 422)
        self.cur.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
