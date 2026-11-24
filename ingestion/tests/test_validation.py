import json
import unittest
from datetime import timezone

from app.validation import MessageInvalide, lire_mesure


class TestValidation(unittest.TestCase):
    topic = "jaden/expl-1/p1/sol/humidite"
    mesure = {"valeur": 31.2, "unite": "%", "ts": "2026-11-16T10:00:00Z", "capteur": "p1-sol"}

    def lire(self, **modifications):
        return lire_mesure(self.topic, json.dumps({**self.mesure, **modifications}).encode())

    def test_mesure_valide(self):
        mesure = self.lire()
        self.assertEqual(mesure.valeur, 31.2)
        self.assertEqual(mesure.exploitation, "expl-1")
        self.assertEqual(mesure.ts.tzinfo, timezone.utc)

    def test_epoch_et_fuseau(self):
        a = self.lire(ts="2026-11-16T06:00:00-04:00")
        b = self.lire(ts=a.ts.timestamp())
        self.assertEqual(a.ts, b.ts)

    def test_valeur_aberrante_conservee_pour_stockage(self):
        self.assertEqual(self.lire(valeur=999).valeur, 999)

    def test_valeurs_incorrectes(self):
        for valeur in [True, "31", None, float("nan"), float("inf"), 10**400]:
            with self.subTest(valeur=type(valeur)):
                with self.assertRaises(MessageInvalide):
                    self.lire(valeur=valeur)

    def test_horodatages_incorrects(self):
        for ts in [True, None, "hier", "2026-11-16T10:00:00", float("inf")]:
            with self.assertRaises(MessageInvalide):
                self.lire(ts=ts)

    def test_unite_et_capteur_incorrects(self):
        for modifications in [{"unite": "°C"}, {"capteur": "p2-sol"}]:
            with self.assertRaises(MessageInvalide):
                self.lire(**modifications)

    def test_topics_incorrects(self):
        for topic in ["jaden/expl-1/p1/vanne/cmd", "jaden/expl-1/p1/statut", "autre/expl-1/p1/sol/humidite", "jaden/+/p1/sol/humidite"]:
            with self.assertRaises(MessageInvalide):
                lire_mesure(topic, json.dumps(self.mesure).encode())

    def test_messages_incorrects(self):
        for payload in [b"{", b"[]", b"{}", b"\xff", b"x" * 4097]:
            with self.assertRaises(MessageInvalide):
                lire_mesure(self.topic, payload)
