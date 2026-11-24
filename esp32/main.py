"""
Capteur d'humidité du sol — ESP32 sous MicroPython (réel ou simulé sur https://wokwi.com)

Matériel : ESP32 + capteur capacitif d'humidité du sol sur la broche GPIO34 (entrée analogique)
           + LED sur GPIO2 pour figurer la vanne (ou relais pour une vraie électrovanne).

Cycle : réveil → mesure → publication MQTT (QoS 1) → écoute brève des commandes → sommeil.
Remarque : pendant le sommeil profond, l'objet ne reçoit pas les commandes. Le serveur doit
donc publier les commandes en message RETENU, ou gérer un état désiré (jumeau numérique).

À adapter : WIFI_SSID, WIFI_MDP, BROKER, EXPLOITATION, PARCELLE, étalonnage SEC/HUMIDE.
"""
import json
import time

import machine
import network
from umqtt.simple import MQTTClient

WIFI_SSID, WIFI_MDP = "Wokwi-GUEST", ""
BROKER = "broker.exemple.local"          # adresse de votre broker
EXPLOITATION, PARCELLE = "expl-1", "p1"
PERIODE_S = 300                          # une mesure toutes les 5 min
SEC, HUMIDE = 3200, 1300                 # lectures ADC à étalonner (sol sec / sol saturé)

BASE = "jaden/{}/{}".format(EXPLOITATION, PARCELLE)
adc = machine.ADC(machine.Pin(34))
adc.atten(machine.ADC.ATTN_11DB)         # plage 0–3,3 V
vanne = machine.Pin(2, machine.Pin.OUT)


def wifi():
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    if not sta.isconnected():
        sta.connect(WIFI_SSID, WIFI_MDP)
        for _ in range(40):
            if sta.isconnected():
                break
            time.sleep(0.25)
    return sta.isconnected()


def humidite_pourcent():
    brut = sum(adc.read() for _ in range(10)) / 10       # moyenne de 10 lectures
    pct = (SEC - brut) * 100 / (SEC - HUMIDE)
    return round(max(0, min(100, pct)), 1)


def sur_commande(topic, msg):
    try:
        cmd = json.loads(msg)
        if cmd.get("action") == "ouvrir":
            vanne.on()
            time.sleep(min(int(cmd.get("duree_s", 60)), 60))  # démonstration : 60 s max
            vanne.off()
        elif cmd.get("action") == "fermer":
            vanne.off()
    except (ValueError, TypeError):
        pass


def cycle():
    if not wifi():
        return
    c = MQTTClient("capteur-" + PARCELLE, BROKER, keepalive=30)
    c.set_last_will(BASE + "/statut", "offline", retain=True, qos=1)
    c.set_callback(sur_commande)
    c.connect()
    c.publish(BASE + "/statut", "online", retain=True, qos=1)
    c.subscribe(BASE + "/vanne/cmd", qos=1)
    mesure = {"valeur": humidite_pourcent(), "unite": "%", "ts": time.time(), "capteur": PARCELLE + "-sol"}
    c.publish(BASE + "/sol/humidite", json.dumps(mesure), qos=1)
    fin = time.ticks_add(time.ticks_ms(), 3000)          # 3 s pour recevoir une commande retenue
    while time.ticks_diff(fin, time.ticks_ms()) > 0:
        c.check_msg()
        time.sleep_ms(100)
    c.disconnect()


cycle()
# Sommeil profond : la carte redémarre et relance main.py à la fin du délai.
# Pendant la mise au point, remplacez par : time.sleep(PERIODE_S) dans une boucle.
machine.deepsleep(PERIODE_S * 1000)
