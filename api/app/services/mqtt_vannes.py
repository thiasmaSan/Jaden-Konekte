
import json
import logging
import threading
from pathlib import Path

import paho.mqtt.client as mqtt
from psycopg.rows import dict_row

from ..config import settings
from ..database import get_connection

logger = logging.getLogger(__name__)

_client = None
_verrou = threading.Lock()
_connecte = threading.Event()


def _identifiants(client):
    mot_de_passe = settings.mqtt_password

    if settings.mqtt_password_file:
        mot_de_passe = Path(
            settings.mqtt_password_file
        ).read_text().strip()

    client.username_pw_set(
        settings.mqtt_user,
        mot_de_passe,
    )


def _confirmation(topic, payload):
    parties = topic.split("/")

    if (
        len(parties) != 5
        or parties[0] != "jaden"
        or parties[3:] != ["vanne", "etat"]
    ):
        return

    exploitation_code = parties[1]
    parcelle_code = parties[2]

    try:
        donnees = json.loads(payload)
    except (ValueError, UnicodeDecodeError):
        return

    if not isinstance(donnees, dict):
        return

    etat = donnees.get("etat")
    commande_id = donnees.get("derniere_cmd")

    if etat not in ("ouverte", "fermee"):
        return

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT e.id
                FROM equipement e
                JOIN parcelle p ON p.id = e.parcelle
                JOIN exploitation x
                  ON x.id = p.exploitation
                WHERE x.code = %s
                  AND p.code = %s
                  AND e.type = 'vanne'
                ORDER BY e.id
                LIMIT 1
                """,
                (exploitation_code, parcelle_code),
            )
            equipement = cur.fetchone()

            if equipement is None:
                return

            equipement_id = equipement["id"]

            # Une confirmation doit correspondre
            # à une commande enregistrée.
            if commande_id:
                cur.execute(
                    """
                    SELECT id, action, statut
                    FROM commande
                    WHERE id = %s
                      AND equipement = %s
                    FOR UPDATE
                    """,
                    (commande_id, equipement_id),
                )
                commande = cur.fetchone()

                if commande is None:
                    return

                etat_attendu = (
                    "ouverte"
                    if commande["action"] == "ouvrir"
                    else "fermee"
                )

                if etat != etat_attendu and commande["statut"] != "confirmee":
                    return

                cur.execute(
                    """
                    UPDATE commande
                    SET statut = 'confirmee'
                    WHERE id = %s
                      AND statut = 'envoyee'
                    """,
                    (commande_id,),
                )

            # Met à jour l'état connu.
            cur.execute(
                """
                UPDATE equipement
                SET etat = %s,
                    maj_le = now()
                WHERE id = %s
                """,
                (etat, equipement_id),
            )


def _on_connect(client, userdata, flags,
                reason_code, properties):
    if reason_code == 0:
        _connecte.set()
        client.subscribe(
            "jaden/+/+/vanne/etat",
            qos=1,
        )
    else:
        _connecte.clear()
        logger.error(
            "Connexion MQTT refusée : %s",
            reason_code,
        )


def _on_disconnect(client, userdata,
                   disconnect_flags,
                   reason_code, properties):
    _connecte.clear()


def _on_message(client, userdata, message):
    try:
        _confirmation(
            message.topic,
            message.payload.decode("utf-8"),
        )
    except Exception:
        logger.exception(
            "Erreur de traitement confirmation MQTT"
        )


def demarrer_mqtt():
    global _client

    with _verrou:
        if _client is not None:
            return

        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="jaden-api-vannes",
        )

        _identifiants(client)

        client.on_connect = _on_connect
        client.on_disconnect = _on_disconnect
        client.on_message = _on_message

        client.connect_async(
            settings.mqtt_host,
            settings.mqtt_port,
            keepalive=30,
        )
        client.loop_start()
        _client = client


def arreter_mqtt():
    global _client

    with _verrou:
        if _client is None:
            return

        _client.disconnect()
        _client.loop_stop()
        _client = None
        _connecte.clear()


def publier_commande(topic, donnees):
    if _client is None or not _connecte.is_set():
        raise RuntimeError(
            "Service MQTT indisponible"
        )

    resultat = _client.publish(
        topic,
        json.dumps(donnees),
        qos=1,
        retain=False,
    )

    if resultat.rc != mqtt.MQTT_ERR_SUCCESS:
        raise RuntimeError(
            "Publication MQTT refusée"
        )

    # Attend l'accusé de réception du broker.
    resultat.wait_for_publish(timeout=5)

    if not resultat.is_published():
        raise RuntimeError(
            "Publication MQTT non confirmée"
        )
