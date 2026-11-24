import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "secret-de-test-utilise-uniquement-dans-les-tests")

from fastapi.testclient import TestClient
from app.main import app
from app.security.dependencies import utilisateur_connecte


class TestLectureParcelles(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.patch = patch("app.routers.parcelles.get_connection")
        connexion = self.patch.start()
        self.cur = MagicMock()
        connexion.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = self.cur
        self.parcelle = {"id": 42, "exploitation": 2, "code": "p1", "nom": "Tomates",
                         "culture": "tomate", "surface_m2": None, "seuil_sec": 25}

    def tearDown(self):
        app.dependency_overrides.clear()
        self.patch.stop()
        self.client.close()

    def test_authentification_obligatoire(self):
        for chemin in ["", "/1", "/1/mesures"]:
            with self.subTest(chemin=chemin):
                r = self.client.get("/api/v1/parcelles" + chemin)
                self.assertEqual(r.status_code, 401)
                self.assertEqual(r.headers["content-type"], "application/problem+json")
                self.assertEqual(r.headers["www-authenticate"], "Bearer")
        self.cur.execute.assert_not_called()

    def test_parcelle_et_mesures_inaccessibles(self):
        app.dependency_overrides[utilisateur_connecte] = lambda: 7
        self.cur.fetchone.return_value = None
        for suffixe in ["", "/mesures"]:
            self.cur.reset_mock()
            r = self.client.get("/api/v1/parcelles/42" + suffixe)
            self.assertEqual(r.status_code, 404)
            self.assertEqual(self.cur.execute.call_count, 1)
            self.assertEqual(self.cur.execute.call_args.args[1], (42, 7))
            self.cur.fetchall.assert_not_called()

    def test_parcelle_accessible(self):
        app.dependency_overrides[utilisateur_connecte] = lambda: 7
        self.cur.fetchone.return_value = self.parcelle
        r = self.client.get("/api/v1/parcelles/42")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), self.parcelle)
        self.assertEqual(self.cur.execute.call_args.args[1], (42, 7))

    def test_liste_filtree_et_paginee(self):
        app.dependency_overrides[utilisateur_connecte] = lambda: 7
        self.cur.fetchall.return_value = [self.parcelle]
        r = self.client.get("/api/v1/parcelles?limit=5&offset=10")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [self.parcelle])
        self.assertEqual(self.cur.execute.call_args.args[1], (7, 5, 10))

    def test_mesures_filtrees_et_paginees(self):
        app.dependency_overrides[utilisateur_connecte] = lambda: 7
        self.cur.fetchone.return_value = self.parcelle
        mesure = {"ts": "2026-11-16T10:00:00Z", "capteur": 3, "valeur": 999, "valide": False}
        self.cur.fetchall.return_value = [mesure]
        r = self.client.get("/api/v1/parcelles/42/mesures?limit=10&offset=20")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()[0]["valide"])
        self.assertEqual(self.cur.execute.call_args.args[1], (42, 10, 20))

    def test_parametres_invalides(self):
        app.dependency_overrides[utilisateur_connecte] = lambda: 7
        for chemin in ["?limit=0", "?offset=-1", "/0", "/1/mesures?limit=1001", "/1/mesures?offset=-1"]:
            with self.subTest(chemin=chemin):
                r = self.client.get("/api/v1/parcelles" + chemin)
                self.assertEqual(r.status_code, 422)
                self.assertEqual(r.headers["content-type"], "application/problem+json")

    def test_agregats_excluent_valeurs_invalides(self):
        app.dependency_overrides[utilisateur_connecte] = lambda: 7
        self.cur.fetchone.return_value = self.parcelle
        self.cur.fetchall.return_value = [{"ts": "2026-11-16T10:00:00Z", "capteur": 3,
                                          "moyenne": 30, "minimum": 20, "maximum": 40, "nombre": 2}]
        r = self.client.get("/api/v1/parcelles/42/mesures/agregats?intervalle=jour&jours=7")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()[0]["nombre"], 2)
        requete, parametres = self.cur.execute.call_args.args
        self.assertIn("m.valide = true", requete)
        self.assertIn("time_bucket", requete)
        self.assertEqual(parametres, ("1 day", 42, 7))

    def test_agregats_inaccessibles(self):
        app.dependency_overrides[utilisateur_connecte] = lambda: 7
        self.cur.fetchone.return_value = None
        r = self.client.get("/api/v1/parcelles/42/mesures/agregats")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.cur.execute.call_count, 1)

    def test_agregats_parametres_invalides(self):
        app.dependency_overrides[utilisateur_connecte] = lambda: 7
        for parametres in ["jours=0", "jours=8", "intervalle=semaine"]:
            r = self.client.get("/api/v1/parcelles/42/mesures/agregats?" + parametres)
            self.assertEqual(r.status_code, 422)
