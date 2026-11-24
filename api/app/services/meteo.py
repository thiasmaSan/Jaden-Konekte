
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from math import isfinite
from time import monotonic

import httpx


URL_METEO = (
    "https://api.open-meteo.com/v1/forecast"
)


class MeteoIndisponible(Exception):
    pass


def recuperer_meteo(
    latitude: float,
    longitude: float,
) -> dict:
    try:
        return _previsions(latitude, longitude, int(monotonic() // 600)).copy()
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as erreur:
        raise MeteoIndisponible("Prévisions météo indisponibles") from erreur


@lru_cache(maxsize=128)
def _previsions(latitude: float, longitude: float, tranche_cache: int) -> dict:
    maintenant = datetime.now(timezone.utc)
    fin = maintenant + timedelta(hours=6)

    parametres = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": (
            "precipitation,"
            "temperature_2m"
        ),
        "forecast_days": 2,
        "timezone": "GMT",
    }

    try:
        with httpx.Client(timeout=8.0) as client:
            reponse = client.get(
                URL_METEO,
                params=parametres,
            )
            reponse.raise_for_status()
            donnees = reponse.json()

    except (
        httpx.HTTPError,
        ValueError,
    ) as erreur:
        raise MeteoIndisponible(
            "Prévisions météo indisponibles"
        ) from erreur

    horaire = donnees.get("hourly", {})
    heures = horaire.get("time", [])
    pluies = horaire.get("precipitation", [])
    temperatures = horaire.get(
        "temperature_2m", []
    )

    if not (
        len(heures)
        == len(pluies)
        == len(temperatures)
    ):
        raise MeteoIndisponible(
            "Réponse météo incomplète"
        )

    cumul_pluie = 0.0
    temperatures_valides = []
    periodes = 0

    for heure, pluie, temperature in zip(
        heures, pluies, temperatures
    ):
        instant = datetime.fromisoformat(
            heure
        ).replace(tzinfo=timezone.utc)

        if maintenant <= instant < fin:
            if pluie is None or not isfinite(float(pluie)) or float(pluie) < 0:
                raise MeteoIndisponible(
                    "Précipitations manquantes"
                )

            cumul_pluie += float(pluie)
            periodes += 1

            if temperature is not None:
                temperatures_valides.append(
                    float(temperature)
                )

    if periodes != 6:
        raise MeteoIndisponible(
            "Aucune prévision exploitable"
        )

    temperature_moyenne = (
        sum(temperatures_valides)
        / len(temperatures_valides)
        if temperatures_valides
        else None
    )

    return {
        "pluie_prevue_mm": round(
            cumul_pluie, 2
        ),
        "temperature_moyenne_c":
            temperature_moyenne,
        "horizon_heures": 6,
        "source": "Open-Meteo",
    }
