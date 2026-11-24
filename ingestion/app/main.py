import logging
import os
import signal
from pathlib import Path

import paho.mqtt.client as mqtt
import psycopg

from .stockage import Stockage
from .validation import GRANDEURS, MessageInvalide, lire_mesure

LOGGER = logging.getLogger("ingestion")


def traiter_message(client, stockage, message):
    try:
        mesure = lire_mesure(message.topic, message.payload)
        resultat = stockage.enregistrer(mesure)
    except MessageInvalide as erreur:
        # Rejet définitif : pas de payload ni de secret dans les logs.
        LOGGER.warning("Message rejeté : %s", erreur)
    else:
        LOGGER.info("Mesure %s : %s", resultat, message.topic)
    # Une erreur SQL remonte sans ACK : le service redémarre et le broker
    # conserve le message QoS 1 dans sa session persistante pour réessayer.
    if message.qos > 0:
        client.ack(message.mid, message.qos)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stockage = Stockage(os.environ["DATABASE_URL"])
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id="jaden-ingestion", clean_session=False, manual_ack=True)
    password = Path(os.environ["MQTT_PASSWORD_FILE"]).read_text().strip()
    client.username_pw_set(os.getenv("MQTT_USER", "ingestion"), password)
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    def connecter(c, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            raise RuntimeError("Connexion au broker refusée")
        for type_capteur, grandeur in GRANDEURS:
            c.subscribe(f"jaden/+/+/{type_capteur}/{grandeur}", qos=1)
        LOGGER.info("Connecté au broker ; abonnements aux mesures demandés")

    client.on_connect = connecter
    client.on_message = lambda c, u, msg: traiter_message(c, stockage, msg)
    signal.signal(signal.SIGTERM, lambda *args: client.disconnect())
    signal.signal(signal.SIGINT, lambda *args: client.disconnect())
    client.connect_async(os.getenv("MQTT_HOST", "mqtt"), int(os.getenv("MQTT_PORT", "1883")), 30)
    try:
        client.loop_forever(retry_first_connection=True)
    except (psycopg.Error, RuntimeError):
        LOGGER.error("Service interrompu ; une reconnexion sera tentée au redémarrage")
        return 1
    finally:
        client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
