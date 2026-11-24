import os
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "secret-de-test-utilise-uniquement-dans-les-tests")

import yaml
from fastapi.testclient import TestClient
from psycopg import OperationalError
from app.main import app
from app.security.dependencies import utilisateur_connecte


class TestContrat(unittest.TestCase):
    def test_schemas_du_contrat(self):
        contrat = yaml.safe_load((Path(__file__).resolve().parents[2] / "openapi.yaml").read_text())
        genere = app.openapi()

        def normaliser(schema):
            if isinstance(schema, list):
                return sorted([normaliser(v) for v in schema], key=str)
            if not isinstance(schema, dict):
                return schema
            resultat = {}
            for cle, valeur in schema.items():
                if cle in ("title", "description", "examples", "default"):
                    continue
                if cle == "properties":
                    resultat[cle] = {nom: normaliser(v) for nom, v in valeur.items()}
                else:
                    resultat[cle] = normaliser(valeur)
            if "anyOf" in resultat and all(set(v) == {"type"} for v in resultat["anyOf"]):
                resultat["type"] = sorted(v["type"] for v in resultat.pop("anyOf"))
            if isinstance(resultat.get("type"), list):
                resultat["type"] = sorted(resultat["type"])
            if resultat.get("type") == "integer" and resultat.get("exclusiveMinimum") == 0:
                resultat.pop("exclusiveMinimum")
                resultat["minimum"] = 1
            return resultat

        from app.schemas.systeme import Probleme
        schemas = {**genere["components"]["schemas"], "Probleme": Probleme.model_json_schema()}
        for nom, schema in contrat["components"]["schemas"].items():
            with self.subTest(schema=nom):
                self.assertIn(nom, schemas)
                self.assertEqual(normaliser(schema), normaliser(schemas[nom]))

    def test_operations_reponses_et_securite(self):
        contrat = yaml.safe_load((Path(__file__).resolve().parents[2] / "openapi.yaml").read_text())
        app.openapi_schema = None
        with warnings.catch_warnings(record=True) as avertissements:
            genere = app.openapi()
        self.assertEqual(avertissements, [])
        self.assertEqual(set(contrat["paths"]), set(genere["paths"]))
        for chemin, operations in contrat["paths"].items():
            self.assertEqual(set(operations), set(genere["paths"][chemin]))
            for methode, operation in operations.items():
                with self.subTest(chemin=chemin, methode=methode):
                    reel = genere["paths"][chemin][methode]
                    self.assertEqual(operation["operationId"], reel["operationId"])
                    self.assertEqual(operation.get("security", []), reel.get("security", []))
                    self.assertEqual(set(operation["responses"]), set(reel["responses"]))
                    for code, reponse in operation["responses"].items():
                        if "$ref" in reponse:
                            reponse = contrat["components"]["responses"][reponse["$ref"].split("/")[-1]]
                        self.assertEqual(set(reponse.get("content", {})), set(reel["responses"][code].get("content", {})))
                    attendus = []
                    for parametre in operation.get("parameters", []):
                        if "$ref" in parametre:
                            parametre = contrat["components"]["parameters"][parametre["$ref"].split("/")[-1]]
                        attendus.append((parametre["name"], parametre["in"]))
                    self.assertEqual(set(attendus), {(p["name"], p["in"]) for p in reel.get("parameters", [])})
        # Les routes de lecture exposent des schémas de sortie, et non un objet vide.
        for chemin in ["/api/v1/parcelles", "/api/v1/parcelles/{id}", "/api/v1/parcelles/{id}/mesures"]:
            self.assertTrue(genere["paths"][chemin]["get"]["responses"]["200"]["content"]["application/json"]["schema"])


class TestErreurs(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.client.close()

    def test_base_indisponible(self):
        app.dependency_overrides[utilisateur_connecte] = lambda: 7
        with patch("app.routers.parcelles.get_connection", side_effect=OperationalError("information confidentielle")):
            reponse = self.client.get("/api/v1/parcelles")
        self.assertEqual(reponse.status_code, 503)
        self.assertEqual(reponse.headers["content-type"], "application/problem+json")
        self.assertNotIn("confidentielle", reponse.text)

    def test_erreur_interne_masquee(self):
        app.dependency_overrides[utilisateur_connecte] = lambda: 7
        with patch("app.routers.parcelles.get_connection", side_effect=RuntimeError("information confidentielle")):
            reponse = self.client.get("/api/v1/parcelles")
        self.assertEqual(reponse.status_code, 500)
        self.assertNotIn("confidentielle", reponse.text)
        self.assertEqual(reponse.headers["content-type"], "application/problem+json")

    def test_route_absente(self):
        reponse = self.client.get("/route-inexistante")
        self.assertEqual(reponse.status_code, 404)
        self.assertEqual(reponse.json()["instance"], "/route-inexistante")
