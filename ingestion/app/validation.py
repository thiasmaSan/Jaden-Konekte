import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone


# Bornes pédagogiques ; modifiables par capteur via min_valide / max_valide.
GRANDEURS = {
    ("sol", "humidite"): ("%", 0, 100),
    ("air", "temperature"): ("°C", -20, 65),
    ("air", "luminosite"): ("lx", 0, 150000),
    ("pluvio", "intensite"): ("mm/h", 0, 500),
}
CODE = re.compile(r"^[A-Za-z0-9_-]{1,30}$")


class MessageInvalide(ValueError):
    pass


@dataclass(frozen=True)
class MesureRecue:
    exploitation: str
    parcelle: str
    type: str
    grandeur: str
    valeur: float
    unite: str
    ts: datetime


def lire_mesure(topic: str, payload: bytes) -> MesureRecue:
    morceaux = topic.split("/")
    if len(morceaux) != 5 or morceaux[0] != "jaden":
        raise MessageInvalide("Topic de mesure invalide")
    _, exploitation, parcelle, type_capteur, grandeur = morceaux
    if not CODE.fullmatch(exploitation) or not CODE.fullmatch(parcelle):
        raise MessageInvalide("Code d'exploitation ou de parcelle invalide")
    if (type_capteur, grandeur) not in GRANDEURS:
        raise MessageInvalide("Grandeur inconnue")
    if len(payload) > 4096:
        raise MessageInvalide("Message trop volumineux")
    try:
        donnees = json.loads(payload)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise MessageInvalide("JSON invalide")
    if not isinstance(donnees, dict):
        raise MessageInvalide("Un objet JSON est attendu")
    if not {"valeur", "unite", "ts", "capteur"}.issubset(donnees):
        raise MessageInvalide("Champs obligatoires manquants")
    valeur = donnees["valeur"]
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        raise MessageInvalide("La valeur doit être un nombre")
    try:
        valeur = float(valeur)
    except OverflowError:
        raise MessageInvalide("Nombre non représentable")
    if not math.isfinite(valeur):
        raise MessageInvalide("Nombre non fini")
    if donnees["unite"] != GRANDEURS[(type_capteur, grandeur)][0]:
        raise MessageInvalide("Unité incohérente avec le topic")
    if not isinstance(donnees["capteur"], str) or donnees["capteur"] != f"{parcelle}-{type_capteur}":
        raise MessageInvalide("Identifiant capteur incohérent avec le topic")
    horodatage = donnees["ts"]
    try:
        if isinstance(horodatage, (float, int)) and not isinstance(horodatage, bool):
            ts = datetime.fromtimestamp(horodatage, timezone.utc)
        elif isinstance(horodatage, str):
            ts = datetime.fromisoformat(horodatage.replace("Z", "+00:00"))
            if ts.tzinfo is None or ts.utcoffset() is None:
                raise ValueError("Fuseau manquant")
            ts = ts.astimezone(timezone.utc)
        else:
            raise ValueError("Type invalide")
    except (ValueError, OverflowError, OSError):
        raise MessageInvalide("Horodatage invalide ou sans fuseau")
    return MesureRecue(exploitation, parcelle, type_capteur, grandeur,
                       valeur, donnees["unite"], ts)
