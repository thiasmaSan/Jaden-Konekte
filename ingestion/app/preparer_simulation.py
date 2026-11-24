"""Prépare p1/p2/p3 dans une exploitation existante, sans écraser les parcelles."""
import argparse
import re
import time

import psycopg


def preparer(database_url, exploitation_id):
    with psycopg.connect(database_url, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT code FROM exploitation WHERE id = %s FOR UPDATE", (exploitation_id,))
            exploitation = cur.fetchone()
            if exploitation is None:
                raise ValueError("Exploitation inexistante")
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,30}", exploitation[0]):
                raise ValueError("Le code d'exploitation n'est pas compatible avec les topics MQTT")
            for code, culture in [("p1", "tomate"), ("p2", "igname"), ("p3", "christophine")]:
                cur.execute(
                    """INSERT INTO parcelle (exploitation, code, nom, culture)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (exploitation, code) DO NOTHING""",
                    (exploitation_id, code, f"Parcelle {code}", culture),
                )
            cur.execute(
                """INSERT INTO equipement (parcelle, type)
                SELECT p.id, 'vanne'
                FROM parcelle p
                WHERE p.exploitation = %s AND p.code IN ('p1', 'p2', 'p3')
                  AND NOT EXISTS (
                    SELECT 1 FROM equipement e WHERE e.parcelle = p.id AND e.type = 'vanne'
                  )""",
                (exploitation_id,),
            )
    return exploitation[0]


def main():
    import os
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exploitation-id", required=True, type=int)
    args = parser.parse_args()
    if args.exploitation_id <= 0:
        parser.error("L'identifiant doit être positif")
    for tentative in range(10):
        try:
            code = preparer(os.environ["DATABASE_URL"], args.exploitation_id)
            print(f"Parcelles p1/p2/p3 prêtes dans {code} ; les parcelles existantes sont conservées")
            return 0
        except psycopg.OperationalError:
            if tentative == 9:
                print("Base indisponible : vérifier le service db")
                return 1
            time.sleep(2)
        except (ValueError, psycopg.Error) as erreur:
            print(str(erreur) if isinstance(erreur, ValueError) else "Échec de préparation SQL")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
