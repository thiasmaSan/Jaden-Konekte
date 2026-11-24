import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "secret-de-test-utilise-uniquement-dans-les-tests")

from fastapi.testclient import TestClient

from app.main import app
from app.security.dependencies import utilisateur_connecte
from app.services import arrosage, meteo, mqtt_vannes, rag


class TestParcoursTableauDeBord(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.addCleanup(app.dependency_overrides.clear)

    def test_evenements_enregistres_et_proteges(self):
        reponse = self.client.get("/api/v1/parcelles/1/evenements")
        self.assertEqual(reponse.status_code, 401)

    def test_assistant_s_abstient_sans_passage_pertinent(self):
        app.dependency_overrides[utilisateur_connecte] = lambda: 1
        with (
            patch.object(rag, "embeddings", AsyncMock(return_value=["[1]"])),
            patch.object(rag, "rechercher", return_value=[{"distance": 0.9}]),
        ):
            reponse = self.client.post("/api/v1/assistant/questions", json={"question": "Question hors corpus"})
        self.assertEqual(reponse.status_code, 200)
        self.assertIn("event: fin", reponse.text)
        self.assertIn(rag.HORS_CORPUS, reponse.text)
        self.assertIn('"sources": []', reponse.text)

    def test_mesure_invalide_ne_declenche_pas_la_regle(self):
        regle = {"id": 1, "parcelle": 1, "condition": {
            "latitude": 16, "longitude": -61, "seuil": 25, "delai_min_s": 3600,
        }, "action": {"duree_s": 600}}
        connexion = MagicMock()
        curseur = connexion.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        curseur.fetchone.side_effect = [{"exploitation": 1}, {"valeur": 2, "valide": False}]
        with (
            patch.object(arrosage, "get_connection", connexion),
            patch.object(arrosage, "recuperer_meteo", return_value={"pluie_prevue_mm": 0}),
            patch.object(arrosage, "publier_commande") as publier,
        ):
            arrosage.evaluer_regle(regle)
        publier.assert_not_called()
        self.assertEqual(curseur.execute.call_count, 2)

    def test_fermeture_minutee_met_a_jour_une_vanne_deja_confirmee(self):
        connexion = MagicMock()
        curseur = connexion.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        curseur.fetchone.side_effect = [{"id": 3}, {"action": "ouvrir", "statut": "confirmee"}]
        with patch.object(mqtt_vannes, "get_connection", connexion):
            mqtt_vannes._confirmation("jaden/expl/p1/vanne/etat", '{"etat":"fermee","derniere_cmd":"cmd-7"}')
        self.assertEqual(curseur.execute.call_args.args[1], ("fermee", 3))

    def test_previsions_en_cache(self):
        maintenant = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        heures = [(maintenant + timedelta(hours=i)).replace(tzinfo=None).isoformat() for i in range(8)]
        reponse = MagicMock()
        reponse.json.return_value = {"hourly": {
            "time": heures, "precipitation": [0] * 8, "temperature_2m": [25] * 8,
        }}
        client = MagicMock()
        client.return_value.__enter__.return_value.get.return_value = reponse
        meteo._previsions.cache_clear()
        self.addCleanup(meteo._previsions.cache_clear)
        with patch.object(meteo.httpx, "Client", client), patch.object(meteo, "monotonic", return_value=100):
            self.assertEqual(meteo.recuperer_meteo(16, -61)["pluie_prevue_mm"], 0)
            self.assertEqual(meteo.recuperer_meteo(16, -61)["temperature_moyenne_c"], 25)
        client.assert_called_once()
