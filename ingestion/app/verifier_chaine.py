"""Vérification réelle MQTT → PostgreSQL ; ajoute une parcelle de test conservée."""
import argparse
import json
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import paho.mqtt.client as mqtt
import psycopg


def connecter(utilisateur=None, fichier=None):
    evenement = threading.Event()
    resultat = []
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="verification-" + uuid.uuid4().hex)
    if utilisateur:
        client.username_pw_set(utilisateur, Path(fichier).read_text().strip())

    def connexion(c, u, flags, reason_code, properties):
        resultat.append(not reason_code.is_failure)
        evenement.set()

    client.on_connect = connexion
    client.connect(os.getenv("MQTT_HOST", "mqtt"), 1883, 30)
    client.loop_start()
    if not evenement.wait(5):
        client.disconnect()
        client.loop_stop()
        raise RuntimeError("Aucune réponse du broker")
    return client, resultat[0]


def fermer(client):
    client.disconnect()
    client.loop_stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exploitation-id", required=True, type=int)
    args = parser.parse_args()
    database_url = os.environ["DATABASE_URL"]
    code = "test-ingestion-" + uuid.uuid4().hex[:8]
    with psycopg.connect(database_url, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT code FROM exploitation WHERE id = %s", (args.exploitation_id,))
            exploitation = cur.fetchone()
            if exploitation is None:
                raise RuntimeError("Exploitation inexistante")
            cur.execute(
                """INSERT INTO parcelle (exploitation, code, nom, culture)
                VALUES (%s, %s, 'Vérification ingestion', 'tomate') RETURNING id""",
                (args.exploitation_id, code),
            )
            parcelle_id = cur.fetchone()[0]
    print(f"Parcelle de test créée : id={parcelle_id}, code={code} (conservée après le test)", flush=True)
    anonyme, autorise = connecter()
    fermer(anonyme)
    if autorise:
        raise RuntimeError("Le broker accepte encore les connexions anonymes")
    print("Connexion anonyme refusée : OK", flush=True)

    client, autorise = connecter("simulateur", "/run/credentials/simulateur/password")
    if not autorise:
        fermer(client)
        raise RuntimeError("Authentification du compte simulateur refusée")
    observateur, lecture_autorisee = connecter("ingestion", "/run/credentials/ingestion/password")
    if not lecture_autorisee:
        fermer(client)
        fermer(observateur)
        raise RuntimeError("Authentification du compte ingestion refusée")
    abonne = threading.Event()
    abonnement_refuse = []
    recus = set()

    def abonnement(c, u, mid, reason_codes, properties):
        abonnement_refuse.append(any(code.is_failure for code in reason_codes))
        abonne.set()

    observateur.on_subscribe = abonnement
    observateur.on_message = lambda c, u, msg: recus.add(msg.topic)
    observateur.subscribe("jaden/+/+/sol/humidite", qos=1)
    if not abonne.wait(5) or abonnement_refuse[0]:
        fermer(client)
        fermer(observateur)
        raise RuntimeError("Abonnement de vérification non confirmé")
    topic = f"jaden/{exploitation[0]}/{code}/sol/humidite"
    maintenant = datetime.now(timezone.utc) - timedelta(seconds=2)
    valide = {"valeur": 31.2, "unite": "%", "ts": maintenant.isoformat(), "capteur": f"{code}-sol"}
    aberrante = {**valide, "valeur": 999, "ts": (maintenant + timedelta(seconds=1)).isoformat()}
    try:
        interdit = f"jaden/hors-scope-{uuid.uuid4().hex[:8]}/{code}/sol/humidite"
        publication = client.publish(interdit, json.dumps(valide), qos=1)
        publication.wait_for_publish(timeout=5)
        time.sleep(1)
        if interdit in recus:
            raise RuntimeError("Les ACL autorisent une publication dans une autre exploitation")
        print("Publication hors exploitation bloquée par les ACL : OK", flush=True)
        for donnees in [valide, valide, aberrante]:
            publication = client.publish(topic, json.dumps(donnees), qos=1)
            publication.wait_for_publish(timeout=5)
            if not publication.is_published():
                raise RuntimeError("Publication MQTT non confirmée")
    finally:
        fermer(client)
        fermer(observateur)
    limite = time.monotonic() + 20
    while time.monotonic() < limite:
        with psycopg.connect(database_url, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT count(*), count(*) FILTER (WHERE m.valide),
                    count(*) FILTER (WHERE NOT m.valide)
                    FROM mesure AS m JOIN capteur AS c ON c.id = m.capteur
                    WHERE c.parcelle = %s""", (parcelle_id,),
                )
                total, bonnes, mauvaises = cur.fetchone()
        if (total, bonnes, mauvaises) == (2, 1, 1):
            print("Chaîne MQTT → TimescaleDB : OK ; 1 valide, 1 aberrante, doublon ignoré", flush=True)
            return 0
        time.sleep(0.5)
    raise RuntimeError("Mesures attendues non retrouvées : vérifier l'ingestion et le code autorisé par les ACL")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, psycopg.Error, OSError) as erreur:
        print(str(erreur) if isinstance(erreur, RuntimeError) else "Échec de connexion ; vérifier les services")
        raise SystemExit(1)
