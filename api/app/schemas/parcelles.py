from decimal import Decimal
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def schema_numerique(schema):
    """L'API reçoit des nombres JSON, même si Decimal accepte aussi du texte en Python."""
    for nom in ("surface_m2", "seuil_sec"):
        propriete = schema["properties"][nom]
        nombre = {
            "type": "number", "multipleOf": 0.01,
            **({"exclusiveMinimum": 0, "maximum": 99999999.99} if nom == "surface_m2"
               else {"minimum": 0, "maximum": 100}),
        }
        propriete.pop("anyOf", None)
        propriete.update(nombre)
        if nom == "surface_m2":
            propriete["type"] = ["number", "null"]
        if isinstance(propriete.get("default"), str):
            propriete["default"] = float(propriete["default"])


def schema_modification(schema):
    schema_numerique(schema)
    schema["minProperties"] = 1
    for nom in ("nom", "culture", "seuil_sec"):
        propriete = schema["properties"][nom]
        if "anyOf" in propriete:
            propriete.update(next(p for p in propriete.pop("anyOf") if p.get("type") != "null"))
        propriete.pop("default", None)


class DonneesParcelle(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("surface_m2", "seuil_sec", mode="before", check_fields=False)
    @classmethod
    def verifier_nombre(cls, valeur):
        if valeur is not None and (isinstance(valeur, bool) or not isinstance(valeur, (int, float, Decimal))):
            raise ValueError("Un nombre JSON est attendu")
        return valeur


class CreationParcelle(DonneesParcelle):
    model_config = ConfigDict(json_schema_extra=schema_numerique)

    exploitation: int = Field(gt=0)
    code: str = Field(min_length=1, max_length=30, pattern=r"^[A-Za-z0-9_-]+$")
    nom: str = Field(min_length=1, max_length=80)
    culture: str = Field(min_length=1, max_length=30)
    surface_m2: Optional[Decimal] = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    seuil_sec: Decimal = Field(default=Decimal("25"), ge=0, le=100, decimal_places=2)


class ModificationParcelle(DonneesParcelle):
    model_config = ConfigDict(json_schema_extra=schema_modification)

    nom: Optional[str] = Field(default=None, min_length=1, max_length=80)
    culture: Optional[str] = Field(default=None, min_length=1, max_length=30)
    surface_m2: Optional[Decimal] = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    seuil_sec: Optional[Decimal] = Field(default=None, ge=0, le=100, decimal_places=2)

    @model_validator(mode="after")
    def verifier_modification(self):
        if not self.model_fields_set:
            raise ValueError("Au moins un champ doit être fourni")
        for champ in self.model_fields_set - {"surface_m2"}:
            if getattr(self, champ) is None:
                raise ValueError(f"Le champ {champ} ne peut pas être null")
        return self


class Parcelle(BaseModel):
    id: int
    exploitation: int
    code: str
    nom: str
    culture: str
    surface_m2: Optional[float]
    seuil_sec: Optional[float]


class Mesure(BaseModel):
    ts: datetime
    capteur: int
    valeur: float
    valide: bool


class AgregatMesure(BaseModel):
    ts: datetime
    capteur: int
    moyenne: float
    minimum: float
    maximum: float
    nombre: int
