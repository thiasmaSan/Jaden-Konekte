import json
import unittest
from dataclasses import replace
from unittest.mock import MagicMock, patch

from psycopg import OperationalError

from app.main import traiter_message
from app.stockage import Stockage
from app.validation import MessageInvalide, lire_mesure


class TestStockage(unittest.TestCase):
    def setUp(self):
        self.patch = patch("app.stockage.psycopg.connect")
        self.connecter = self.patch.start()
        self.conn = self.connecter.return_value.__enter__.return_value
        self.cur = self.conn.cursor.return_value.__enter__.return_value
        self.mesure = lire_mesure("jaden/expl-1/p1/sol/humidite", json.dumps({
            "valeur": 31.2, "unite": "%", "ts": "2026-11-16T10:00:00Z", "capteur": "p1-sol",
        }).encode())
        self.stockage = Stockage("postgresql://test")
        self.capteur = {"id": 4, "unite": "%", "actif": True, "min_valide": 0, "max_valide": 100}

    def tearDown(self):
        self.patch.stop()

    def test_declaration_et_insertion(self):
        self.cur.fetchone.side_effect = [{"id": 2}, {"id": 4}, {"capteur": 4}]
        self.cur.fetchall.return_value = []
        self.assertEqual(self.stockage.enregistrer(self.mesure), "enregistree")
        self.assertEqual(self.cur.execute.call_args_list[0].args[1], ("expl-1", "p1"))
        self.assertIn("FOR UPDATE OF p", self.cur.execute.call_args_list[0].args[0])
        self.assertIn("INSERT INTO capteur", self.cur.execute.call_args_list[2].args[0])
        self.assertTrue(self.cur.execute.call_args.args[1][-1])

    def test_doublon_ignore(self):
        self.cur.fetchone.side_effect = [{"id": 2}, None]
        self.cur.fetchall.return_value = [self.capteur]
        self.assertEqual(self.stockage.enregistrer(self.mesure), "doublon")
        self.assertIn("ON CONFLICT (capteur, ts) DO NOTHING", self.cur.execute.call_args.args[0])

    def test_bornes_personnalisees(self):
        self.cur.fetchone.side_effect = [{"id": 2}, {"capteur": 4}]
        self.cur.fetchall.return_value = [{**self.capteur, "max_valide": 30}]
        self.assertEqual(self.stockage.enregistrer(self.mesure), "aberrante")
        self.assertFalse(self.cur.execute.call_args.args[1][-1])

    def test_valeurs_aberrantes_du_simulateur(self):
        for valeur in [-1, 999]:
            with self.subTest(valeur=valeur):
                self.cur.fetchone.side_effect = [{"id": 2}, {"capteur": 4}]
                self.cur.fetchall.return_value = [self.capteur]
                self.assertEqual(self.stockage.enregistrer(replace(self.mesure, valeur=valeur)), "aberrante")
                self.assertFalse(self.cur.execute.call_args.args[1][-1])

    def test_parcelle_inconnue(self):
        self.cur.fetchone.return_value = None
        with self.assertRaises(MessageInvalide):
            self.stockage.enregistrer(self.mesure)
        self.assertEqual(self.cur.execute.call_count, 1)

    def test_capteur_inactif_ou_ambigu(self):
        for capteurs in [[{**self.capteur, "actif": False}], [self.capteur, self.capteur]]:
            self.cur.reset_mock()
            self.cur.fetchone.side_effect = None
            self.cur.fetchone.return_value = {"id": 2}
            self.cur.fetchall.return_value = capteurs
            with self.assertRaises(MessageInvalide):
                self.stockage.enregistrer(self.mesure)
            self.assertEqual(self.cur.execute.call_count, 2)


class TestAcquittement(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.stockage = MagicMock()
        self.message = MagicMock(topic="jaden/expl-1/p1/sol/humidite", mid=42, qos=1)
        self.message.payload = json.dumps({"valeur": 31.2, "unite": "%", "ts": 1794823200, "capteur": "p1-sol"}).encode()

    def test_acquittement_apres_stockage(self):
        ordre = []
        self.stockage.enregistrer.side_effect = lambda mesure: ordre.append("stockage")
        self.client.ack.side_effect = lambda *args: ordre.append("ack")
        traiter_message(self.client, self.stockage, self.message)
        self.assertEqual(ordre, ["stockage", "ack"])

    def test_pas_acquittement_si_base_indisponible(self):
        self.stockage.enregistrer.side_effect = OperationalError()
        with self.assertRaises(OperationalError):
            traiter_message(self.client, self.stockage, self.message)
        self.client.ack.assert_not_called()

    def test_rejet_definitif_message_malforme(self):
        self.message.payload = b"{}"
        with self.assertLogs("ingestion", level="WARNING"):
            traiter_message(self.client, self.stockage, self.message)
        self.stockage.enregistrer.assert_not_called()
        self.client.ack.assert_called_once_with(42, 1)
