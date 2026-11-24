import unittest
from unittest.mock import patch

from app.preparer_simulation import preparer


class TestPreparation(unittest.TestCase):
    def test_parcelles_existantes_preservees(self):
        with patch("app.preparer_simulation.psycopg.connect") as connecter:
            cur = connecter.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cur.fetchone.return_value = ("expl-reelle",)
            self.assertEqual(preparer("postgresql://test", 1), "expl-reelle")
            self.assertEqual(cur.execute.call_args_list[0].args[1], (1,))
            self.assertEqual(cur.execute.call_count, 5)
            for appel in cur.execute.call_args_list[1:4]:
                self.assertIn("ON CONFLICT (exploitation, code) DO NOTHING", appel.args[0])

            self.assertIn("INSERT INTO equipement", cur.execute.call_args.args[0])
            self.assertIn("NOT EXISTS", cur.execute.call_args.args[0])
            self.assertEqual(cur.execute.call_args.args[1], (1,))

    def test_aucune_creation_exploitation_inconnue(self):
        with patch("app.preparer_simulation.psycopg.connect") as connecter:
            cur = connecter.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cur.fetchone.return_value = None
            with self.assertRaises(ValueError):
                preparer("postgresql://test", 99)
            self.assertEqual(cur.execute.call_count, 1)

    def test_code_mqtt_invalide_refuse(self):
        with patch("app.preparer_simulation.psycopg.connect") as connecter:
            cur = connecter.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
            cur.fetchone.return_value = ("expl/invalide",)
            with self.assertRaises(ValueError):
                preparer("postgresql://test", 1)
            self.assertEqual(cur.execute.call_count, 1)
