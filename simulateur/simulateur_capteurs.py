"""
Simulateur de parcelles connectées — Jaden Konekté

Simule, pour une ou plusieurs parcelles, des capteurs (humidité du sol, température de l'air,
luminosité, pluie) et une vanne d'arrosage commandable, qui communiquent en MQTT selon les
conventions du sujet.

    pip install paho-mqtt>=2.0
    python simulateur_capteurs.py --broker localhost --exploitation expl-1 --parcelles p1 p2
    python simulateur_capteurs.py --dry-run          # sans broker : affiche les messages

Options utiles :
    --acceleration 60   1 s réelle = 60 s simulées (une journée en 24 min)
    --periode 10        une mesure toutes les 10 s simulées… réelles (voir --help)
    --user / --password identifiants MQTT (si le broker l'exige)

Topics (voir le sujet, § Conventions MQTT) :
    jaden/<exploitation>/<parcelle>/<capteur>/<grandeur>      mesures (QoS 1)
    jaden/<exploitation>/<parcelle>/vanne/cmd                 commandes reçues
    jaden/<exploitation>/<parcelle>/vanne/etat                état de la vanne (retenu)
    jaden/<exploitation>/<parcelle>/statut                    online / offline (LWT, retenu)

Commande attendue sur .../vanne/cmd (JSON) :
    {"action": "ouvrir", "duree_s": 600, "id": "cmd-42"}   ou   {"action": "fermer", "id": "cmd-43"}
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path


# ------------------------------------------------------------------ modèle physique simplifié
@dataclass
class Parcelle:
    exploitation: str
    nom: str
    humidite_sol: float = field(default_factory=lambda: random.uniform(35, 55))  # % volumique
    vanne_ouverte_jusqua: datetime | None = None
    derniere_cmd: str | None = None
    pluie_restante_min: float = 0.0
    panne_capteur: bool = False

    def base(self) -> str:
        return f"jaden/{self.exploitation}/{self.nom}"


def meteo(t: datetime) -> tuple[float, float]:
    """Température (°C) et luminosité (lux) selon l'heure locale (Guadeloupe, UTC-4)."""
    loc = t - timedelta(hours=4)
    h = loc.hour + loc.minute / 60
    jour = max(0.0, math.sin(math.pi * (h - 6) / 12))           # 0 la nuit, 1 à midi
    temp = 23.5 + 7.0 * jour + random.gauss(0, 0.4)             # ~23 °C nuit, ~30 °C midi
    lux = 95_000 * jour ** 1.3 * random.uniform(0.55, 1.0)       # passages nuageux
    return round(temp, 1), round(lux)


def pas_de_temps(p: Parcelle, t: datetime, dt_min: float) -> dict:
    """Fait évoluer la parcelle de dt_min minutes et renvoie les mesures."""
    temp, lux = meteo(t)

    # averses tropicales : courtes et intenses, plus fréquentes l'après-midi
    h_loc = (t - timedelta(hours=4)).hour
    proba = 0.0005 * dt_min * (2.5 if 13 <= h_loc <= 18 else 1.0)
    if p.pluie_restante_min <= 0 and random.random() < proba:
        p.pluie_restante_min = random.uniform(10, 45)
    pluie_mm_h = 0.0
    if p.pluie_restante_min > 0:
        pluie_mm_h = random.uniform(4, 25)
        p.pluie_restante_min -= dt_min

    arrosage = p.vanne_ouverte_jusqua is not None and t < p.vanne_ouverte_jusqua
    if p.vanne_ouverte_jusqua is not None and t >= p.vanne_ouverte_jusqua:
        p.vanne_ouverte_jusqua = None

    # bilan hydrique très simplifié (pédagogique, non agronomique)
    evapo = (0.002 + 0.0000002 * lux) * (1 + max(0, temp - 25) / 10) * dt_min
    apport = (pluie_mm_h * 0.035 + (0.6 if arrosage else 0.0)) * dt_min
    p.humidite_sol = min(60.0, max(8.0, p.humidite_sol - evapo + apport))

    mesures = {
        ("sol", "humidite"): (round(p.humidite_sol + random.gauss(0, 0.3), 1), "%"),
        ("air", "temperature"): (temp, "°C"),
        ("air", "luminosite"): (lux, "lx"),
        ("pluvio", "intensite"): (round(pluie_mm_h, 1), "mm/h"),
    }
    # panne occasionnelle d'un capteur : valeur aberrante (à détecter par la validation !)
    if random.random() < 0.002:
        p.panne_capteur = not p.panne_capteur
    if p.panne_capteur:
        mesures[("sol", "humidite")] = (random.choice([-1.0, 0.0, 999.0]), "%")
    return {"mesures": mesures, "arrosage": arrosage}


# ------------------------------------------------------------------ MQTT
def payload(valeur, unite: str, t: datetime, capteur_id: str) -> str:
    return json.dumps({"valeur": valeur, "unite": unite, "ts": t.isoformat(timespec="seconds"),
                       "capteur": capteur_id}, ensure_ascii=False)


def etat_vanne(p: Parcelle, t: datetime) -> str:
    ouverte = p.vanne_ouverte_jusqua is not None and t < p.vanne_ouverte_jusqua
    return json.dumps({
        "etat": "ouverte" if ouverte else "fermee",
        "jusqua": p.vanne_ouverte_jusqua.isoformat(timespec="seconds") if ouverte else None,
        "derniere_cmd": p.derniere_cmd,
        "ts": t.isoformat(timespec="seconds"),
    })


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--broker", default="localhost")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--user", default=os.getenv("MQTT_USER"))
    ap.add_argument("--password")
    ap.add_argument("--password-file", default=os.getenv("MQTT_PASSWORD_FILE"))
    ap.add_argument("--exploitation")
    ap.add_argument("--exploitation-file", default=os.getenv("MQTT_EXPLOITATION_FILE"))
    ap.add_argument("--parcelles", nargs="+", default=["p1"])
    ap.add_argument("--periode", type=float, default=5.0, help="secondes réelles entre deux mesures")
    ap.add_argument("--acceleration", type=float, default=60.0, help="facteur d'accélération du temps")
    ap.add_argument("--dry-run", action="store_true", help="n'utilise pas de broker, affiche les messages")
    ap.add_argument("--iterations", type=int, default=0, help="0 = infini")
    a = ap.parse_args()
    if not a.exploitation:
        a.exploitation = Path(a.exploitation_file).read_text().strip() if a.exploitation_file else "expl-1"

    parcelles = {n: Parcelle(a.exploitation, n) for n in a.parcelles}
    t_sim = datetime.now(timezone.utc).replace(microsecond=0)
    client = None

    def publier(topic: str, msg: str, retain: bool = False) -> None:
        if client is None:
            print(f"{topic:<45} {msg}")
        else:
            client.publish(topic, msg, qos=1, retain=retain)

    if not a.dry_run:
        import paho.mqtt.client as mqtt

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sim-{a.exploitation}")
        if a.user:
            password = Path(a.password_file).read_text().strip() if a.password_file else a.password
            client.username_pw_set(a.user, password)
        # une LWT par client MQTT : on la met sur la première parcelle et on publie les autres à la main
        premiere = next(iter(parcelles.values()))
        client.will_set(f"{premiere.base()}/statut", "offline", qos=1, retain=True)

        def on_connect(c, userdata, flags, reason_code, properties):
            print(f"[mqtt] connecté ({reason_code})")
            for p in parcelles.values():
                c.subscribe(f"{p.base()}/vanne/cmd", qos=1)
                c.publish(f"{p.base()}/statut", "online", qos=1, retain=True)
                c.publish(f"{p.base()}/vanne/etat", etat_vanne(p, t_sim), qos=1, retain=True)

        def on_message(c, userdata, msg):
            nom = msg.topic.split("/")[2]
            p = parcelles.get(nom)
            try:
                cmd = json.loads(msg.payload)
                if cmd.get("action") == "ouvrir":
                    duree = max(10, min(int(cmd.get("duree_s", 300)), 3600))
                    p.vanne_ouverte_jusqua = t_sim + timedelta(seconds=duree)
                elif cmd.get("action") == "fermer":
                    p.vanne_ouverte_jusqua = None
                else:
                    raise ValueError("action inconnue")
                p.derniere_cmd = cmd.get("id")
                print(f"[cmd] {msg.topic} {cmd}")
            except (ValueError, TypeError, AttributeError) as e:
                print(f"[cmd] ignorée ({e}) : {msg.payload[:80]!r}")
                return
            c.publish(f"{p.base()}/vanne/etat", etat_vanne(p, t_sim), qos=1, retain=True)

        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(a.broker, a.port, keepalive=30)
        client.loop_start()

    n = 0
    try:
        while a.iterations == 0 or n < a.iterations:
            dt_min = a.periode * a.acceleration / 60
            t_sim += timedelta(minutes=dt_min)
            for p in parcelles.values():
                avant = p.vanne_ouverte_jusqua is not None
                res = pas_de_temps(p, t_sim, dt_min)
                for (capteur, grandeur), (v, u) in res["mesures"].items():
                    publier(f"{p.base()}/{capteur}/{grandeur}", payload(v, u, t_sim, f"{p.nom}-{capteur}"))
                if avant and p.vanne_ouverte_jusqua is None:  # fermeture automatique en fin de durée
                    publier(f"{p.base()}/vanne/etat", etat_vanne(p, t_sim), retain=True)
            n += 1
            time.sleep(0 if a.dry_run else a.periode)
    except KeyboardInterrupt:
        pass
    finally:
        if client is not None:
            for p in parcelles.values():
                client.publish(f"{p.base()}/statut", "offline", qos=1, retain=True)
            client.loop_stop()
            client.disconnect()


if __name__ == "__main__":
    main()
