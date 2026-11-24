
from datetime import datetime, timezone, timedelta

from psycopg.rows import dict_row

from ..database import get_connection
from ..config import settings


def recuperer_tableau_de_bord(parcelle: dict) -> dict:
    """
    Construit l'état actuel d'une parcelle.

    La vérification des droits d'accès est réalisée
    par la dépendance parcelle_accessible avant
    l'appel à cette fonction.
    """

    date_actuelle = datetime.now(timezone.utc)

    delai = timedelta(
        seconds=settings.capteur_delai_hors_ligne_s
    )

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:

            # Dernière mesure valide pour chaque capteur.
            cur.execute(
                """
                SELECT
                    c.id,
                    c.type,
                    c.grandeur,
                    c.unite,
                    c.actif,
                    m.valeur,
                    m.ts
                FROM capteur AS c
                LEFT JOIN LATERAL (
                    SELECT
                        mesure.valeur,
                        mesure.ts
                    FROM mesure
                    WHERE mesure.capteur = c.id
                      AND mesure.valide = TRUE
                      AND mesure.ts <= %s
                    ORDER BY mesure.ts DESC
                    LIMIT 1
                ) AS m ON TRUE
                WHERE c.parcelle = %s
                ORDER BY c.id
                """,
                (date_actuelle, parcelle["id"]),
            )

            lignes_capteurs = cur.fetchall()

            # Équipements de type vanne.
            cur.execute(
                """
                SELECT
                    id,
                    type,
                    etat,
                    maj_le
                FROM equipement
                WHERE parcelle = %s
                  AND type = 'vanne'
                ORDER BY id
                """,
                (parcelle["id"],),
            )

            vannes = cur.fetchall()

    capteurs = []
    total_actifs = 0
    total_en_ligne = 0

    for ligne in lignes_capteurs:

        actif = ligne["actif"]

        if actif:
            total_actifs += 1

        derniere_mesure = None
        en_ligne = False

        if ligne["ts"] is not None:

            derniere_mesure = {
                "valeur": ligne["valeur"],
                "ts": ligne["ts"],
            }

            age = date_actuelle - ligne["ts"]

            en_ligne = (
                actif
                and timedelta(0) <= age <= delai
            )

        if en_ligne:
            total_en_ligne += 1

        capteurs.append({
            "id": ligne["id"],
            "type": ligne["type"],
            "grandeur": ligne["grandeur"],
            "unite": ligne["unite"],
            "actif": actif,
            "en_ligne": en_ligne,
            "derniere_mesure": derniere_mesure,
        })

    return {
        "parcelle": parcelle,
        "capteurs": capteurs,
        "resume_capteurs": {
            "total": len(capteurs),
            "actifs": total_actifs,
            "en_ligne": total_en_ligne,
        },
        "vannes": vannes,
        "actualise_le": date_actuelle,
    }
