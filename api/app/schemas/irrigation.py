from typing import Optional

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class RecommandationIrrigation(BaseModel):
    parcelle_id: int

    humidite_sol: Optional[float]
    seuil_sec: Optional[float]

    pluie_prevue_mm: Optional[float]
    temperature_moyenne_c: Optional[float]

    decision: Literal[
        "arroser",
        "attendre",
        "donnees_insuffisantes",
    ]

    raison: str
    mode: Literal["simulation"] = "simulation"
    source_meteo: Optional[str] = None


class ConfigurationArrosage(BaseModel):
    active: bool = False
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    seuil: float = Field(ge=0, le=100)
    duree_s: int = Field(ge=10, le=3600)
    delai_min_s: int = Field(ge=600, le=604800)

    @model_validator(mode="after")
    def verifier_delai(self):
        if self.delai_min_s < self.duree_s:
            raise ValueError("Le délai minimal doit couvrir la durée d’arrosage")
        return self
