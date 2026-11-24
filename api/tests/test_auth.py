import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "secret-de-test-utilise-uniquement-dans-les-tests")

import jwt
from fastapi.testclient import TestClient
from psycopg.errors import UniqueViolation
from app.main import app
from app.config import settings
from app.security.jwt import creer_jeton, hacher_mot_de_passe, verifier_mot_de_passe


class TestAuthentification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mot_de_passe = "Mot-de-passe-test-2026"
        cls.empreinte = hacher_mot_de_passe(cls.mot_de_passe)

    def setUp(self):
        self.client = TestClient(app)
        self.patch = patch("app.routers.auth.get_connection")
        self.connexion = self.patch.start()
        self.cur = MagicMock()
        self.connexion.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = self.cur
        self.identifiants = {"courriel": "user@example.com", "mot_de_passe": self.mot_de_passe}

    def tearDown(self):
        self.patch.stop()
        self.client.close()

    def test_hachage(self):
        self.assertNotEqual(self.empreinte, self.mot_de_passe)
        self.assertTrue(verifier_mot_de_passe(self.mot_de_passe, self.empreinte))
        self.assertFalse(verifier_mot_de_passe("incorrect", self.empreinte))

    def test_connexion_valide(self):
        self.cur.fetchone.return_value = {"id": 7, "mot_de_passe": self.empreinte}
        r = self.client.post("/api/v1/auth/connexion", json=self.identifiants)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["token_type"], "bearer")
        donnees = jwt.decode(r.json()["access_token"], settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        self.assertEqual(donnees["sub"], "7")
        self.assertGreater(donnees["exp"], donnees["iat"])

    def test_identifiants_incorrects(self):
        for utilisateur in [None, {"id": 7, "mot_de_passe": self.empreinte}]:
            self.cur.fetchone.return_value = utilisateur
            r = self.client.post("/api/v1/auth/connexion", json={**self.identifiants, "mot_de_passe": "incorrect"})
            self.assertEqual(r.status_code, 401)
            self.assertEqual(r.headers["www-authenticate"], "Bearer")
            self.assertNotIn("mot_de_passe", r.json())

    def inscription(self):
        return self.client.post("/api/v1/auth/inscription", json={
            **self.identifiants, "prenom": "Jean", "nom": "Test", "code_exploitation": "expl-test",
            "nom_exploitation": "Jardin test", "commune": "Baillif",
        })

    def test_inscription(self):
        self.cur.fetchone.side_effect = [
            {"id": 7, "prenom": "Jean", "nom": "Test", "courriel": "user@example.com"}, {"id": 2},
        ]
        r = self.inscription()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["exploitation_id"], 2)
        self.assertNotIn("mot_de_passe", r.json())
        self.assertEqual(self.connexion.call_count, 1)
        self.assertEqual(self.cur.execute.call_count, 3)
        self.assertEqual(self.cur.execute.call_args.args[1], (7, 2, "exploitant"))
        valeur_stockee = self.cur.execute.call_args_list[0].args[1][3]
        self.assertTrue(verifier_mot_de_passe(self.mot_de_passe, valeur_stockee))

    def test_doublon_inscription(self):
        self.cur.execute.side_effect = UniqueViolation()
        r = self.inscription()
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.headers["content-type"], "application/problem+json")

    def test_jwt_invalides(self):
        maintenant = datetime.now(timezone.utc)
        base = {"sub": "7", "iat": maintenant, "exp": maintenant + timedelta(minutes=5)}
        jetons = ["invalide", jwt.encode(base, "autre-secret-utilise-uniquement-pour-les-tests", algorithm="HS256")]
        for modifications in [{"exp": maintenant - timedelta(seconds=1)}, {"sub": "0"}, {"sub": "abc"}]:
            jetons.append(jwt.encode({**base, **modifications}, settings.jwt_secret, algorithm=settings.jwt_algorithm))
        jetons.append(jwt.encode({"sub": "7"}, settings.jwt_secret, algorithm=settings.jwt_algorithm))
        for jeton in jetons:
            r = self.client.get("/api/v1/parcelles", headers={"Authorization": "Bearer " + jeton})
            self.assertEqual(r.status_code, 401)
        self.cur.execute.assert_not_called()
