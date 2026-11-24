import psycopg
from psycopg.rows import dict_row

from .validation import GRANDEURS, MessageInvalide, MesureRecue


class Stockage:
    def __init__(self, database_url):
        self.database_url = database_url

    def enregistrer(self, mesure: MesureRecue):
        with psycopg.connect(self.database_url, connect_timeout=5) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # Sérialise la déclaration des capteurs et bloque une suppression
                # concurrente de la parcelle, sans exiger de migration du schéma.
                cur.execute(
                    """SELECT p.id FROM parcelle AS p
                    JOIN exploitation AS e ON e.id = p.exploitation
                    WHERE e.code = %s AND p.code = %s FOR UPDATE OF p""",
                    (mesure.exploitation, mesure.parcelle),
                )
                parcelle = cur.fetchone()
                if parcelle is None:
                    raise MessageInvalide("Parcelle inconnue : créer la parcelle avant de publier")
                cur.execute(
                    """SELECT id, unite, min_valide, max_valide, actif FROM capteur
                    WHERE parcelle = %s AND type = %s AND grandeur = %s""",
                    (parcelle["id"], mesure.type, mesure.grandeur),
                )
                capteurs = cur.fetchall()
                if len(capteurs) > 1:
                    raise MessageInvalide("Plusieurs capteurs correspondent à cette grandeur")
                unite, minimum, maximum = GRANDEURS[(mesure.type, mesure.grandeur)]
                if capteurs:
                    capteur = capteurs[0]
                    if not capteur["actif"] or capteur["unite"] != mesure.unite:
                        raise MessageInvalide("Capteur inactif ou unité incohérente")
                    if capteur["min_valide"] is not None:
                        minimum = float(capteur["min_valide"])
                    if capteur["max_valide"] is not None:
                        maximum = float(capteur["max_valide"])
                    if minimum > maximum:
                        raise MessageInvalide("Bornes du capteur incohérentes")
                else:
                    cur.execute(
                        """INSERT INTO capteur (parcelle, type, grandeur, unite, min_valide, max_valide)
                        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                        (parcelle["id"], mesure.type, mesure.grandeur, unite, minimum, maximum),
                    )
                    capteur = cur.fetchone()
                valide = minimum <= mesure.valeur <= maximum
                cur.execute(
                    """INSERT INTO mesure (ts, capteur, valeur, valide)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (capteur, ts) DO NOTHING RETURNING capteur""",
                    (mesure.ts, capteur["id"], mesure.valeur, valide),
                )
                inseree = cur.fetchone() is not None
        # Le commit est terminé avant le retour et l'accusé de réception MQTT.
        return "doublon" if not inseree else ("enregistree" if valide else "aberrante")
