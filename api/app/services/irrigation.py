from typing import Optional



from .tableau_de_bord import (
    recuperer_tableau_de_bord,
)


PLUIE_SEUIL_MM = 2.0


def analyser_irrigation(
    parcelle: dict,
    meteo: Optional[dict],
) -> dict:

    tableau = recuperer_tableau_de_bord(
        parcelle
    )

    humidite = None
    seuil_sec = parcelle.get("seuil_sec")

    for capteur in tableau["capteurs"]:
        if (
            capteur["type"] != "sol"
            or capteur["grandeur"] != "humidite"
            or not capteur["en_ligne"]
        ):
            continue

        mesure = capteur["derniere_mesure"]

        if mesure is not None:
            humidite = mesure["valeur"]
            break

    resultat = {
        "parcelle_id": parcelle["id"],
        "humidite_sol": humidite,
        "seuil_sec": seuil_sec,
        "pluie_prevue_mm": (
            meteo["pluie_prevue_mm"]
            if meteo else None
        ),
        "temperature_moyenne_c": (
            meteo["temperature_moyenne_c"]
            if meteo else None
        ),
        "decision": "donnees_insuffisantes",
        "raison": "",
        "mode": "simulation",
        "source_meteo": (
            meteo["source"] if meteo else None
        ),
    }

    if humidite is None:
        resultat["raison"] = (
            "Aucune mesure récente "
            "d'humidité du sol."
        )
        return resultat

    if seuil_sec is None:
        resultat["raison"] = (
            "Seuil de sécheresse non défini."
        )
        return resultat

    if humidite >= seuil_sec:
        resultat["decision"] = "attendre"
        resultat["raison"] = (
            "L'humidité du sol est "
            "supérieure ou égale au seuil."
        )
        return resultat

    if meteo is None:
        resultat["raison"] = (
            "Sol sec, mais prévisions "
            "météorologiques indisponibles."
        )
        return resultat

    if (
        meteo["pluie_prevue_mm"]
        >= PLUIE_SEUIL_MM
    ):
        resultat["decision"] = "attendre"
        resultat["raison"] = (
            "Sol sec, mais pluie prévue "
            "dans les prochaines heures."
        )
        return resultat

    resultat["decision"] = "arroser"
    resultat["raison"] = (
        "Humidité sous le seuil "
        "et pluie prévue insuffisante."
    )

    return resultat
