import asyncio
import logging
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..config import settings
from ..database import get_connection
from .irrigation import PLUIE_SEUIL_MM
from .meteo import MeteoIndisponible, recuperer_meteo
from .mqtt_vannes import publier_commande

logger = logging.getLogger(__name__)


def evaluer_regle(regle):
    condition = regle["condition"]
    try:
        meteo = recuperer_meteo(condition["latitude"], condition["longitude"])
    except MeteoIndisponible:
        return
    if meteo["pluie_prevue_mm"] >= PLUIE_SEUIL_MM:
        return

    commande_id = f"cmd-{uuid4().hex}"
    duree = regle["action"]["duree_s"]
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT p.exploitation, p.code, x.code AS exploitation_code
            FROM regle r
            JOIN parcelle p ON p.id = r.parcelle
            JOIN exploitation x ON x.id = p.exploitation
            WHERE r.id = %s AND r.active AND r.condition = %s AND r.action = %s
              AND (r.derniere_execution IS NULL OR
                   r.derniere_execution <= now() - make_interval(secs => %s))
            FOR UPDATE OF r
            """,
            (regle["id"], Jsonb(condition), Jsonb(regle["action"]), condition["delai_min_s"]),
        )
        parcelle = cur.fetchone()
        if not parcelle:
            return

        cur.execute(
            """
            SELECT m.valeur, m.valide
            FROM mesure m
            JOIN capteur c ON c.id = m.capteur
            WHERE c.parcelle = %s AND c.actif
              AND c.type = 'sol' AND c.grandeur = 'humidite'
              AND m.ts BETWEEN now() - make_interval(secs => %s) AND now()
            ORDER BY m.ts DESC, c.id LIMIT 1
            """,
            (regle["parcelle"], settings.capteur_delai_hors_ligne_s),
        )
        mesure = cur.fetchone()
        if not mesure or not mesure["valide"] or mesure["valeur"] >= condition["seuil"]:
            return

        cur.execute(
            """
            SELECT id, etat FROM equipement
            WHERE parcelle = %s AND type = 'vanne'
            ORDER BY id LIMIT 1 FOR UPDATE
            """,
            (regle["parcelle"],),
        )
        vanne = cur.fetchone()
        if not vanne or vanne["etat"] != "fermee":
            return

        cur.execute(
            """SELECT 1 FROM commande WHERE equipement = %s AND action = 'ouvrir'
               AND statut IN ('envoyee', 'confirmee')
               AND cree_le > now() - make_interval(secs => GREATEST(duree_s, %s))
               LIMIT 1""",
            (vanne["id"], condition["delai_min_s"]),
        )
        if cur.fetchone():
            return

        cur.execute(
            """INSERT INTO commande (id, equipement, action, duree_s, origine)
               VALUES (%s, %s, 'ouvrir', %s, 'regle')""",
            (commande_id, vanne["id"], duree),
        )
        cur.execute("UPDATE regle SET derniere_execution = now() WHERE id = %s", (regle["id"],))
        cur.execute(
            "INSERT INTO historique (exploitation, type, details) VALUES (%s, 'regle', %s)",
            (parcelle["exploitation"], Jsonb({
                "parcelle": regle["parcelle"], "commande": commande_id,
                "humidite": mesure["valeur"], "pluie_mm": meteo["pluie_prevue_mm"],
                "duree_s": duree,
            })),
        )

    topic = f"jaden/{parcelle['exploitation_code']}/{parcelle['code']}/vanne/cmd"
    try:
        publier_commande(topic, {"id": commande_id, "action": "ouvrir", "duree_s": duree})
    except RuntimeError:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE commande SET statut = 'echec' WHERE id = %s AND statut = 'envoyee'",
                (commande_id,),
            )
        logger.warning("Publication MQTT non confirmée pour %s", commande_id)


def evaluer_regles():
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, parcelle, condition, action FROM regle WHERE nom = 'Automatique' AND active")
        regles = cur.fetchall()
    for regle in regles:
        try:
            evaluer_regle(regle)
        except Exception:
            logger.exception("Évaluation de la règle %s impossible", regle["id"])


async def planifier_arrosage():
    while True:
        try:
            await asyncio.to_thread(evaluer_regles)
        except Exception:
            logger.exception("Lecture des règles impossible")
        await asyncio.sleep(60)
