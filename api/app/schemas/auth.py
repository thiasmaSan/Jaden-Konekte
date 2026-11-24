
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class Inscription(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    prenom: str = Field(min_length=1, max_length=40)
    nom: str = Field(min_length=1, max_length=40)
    courriel: EmailStr = Field(max_length=120)
    mot_de_passe: str = Field(min_length=12, max_length=128, json_schema_extra={"writeOnly": True})
    code_exploitation: str = Field(min_length=1, max_length=30, pattern=r"^[A-Za-z0-9_-]+$")
    nom_exploitation: str = Field(min_length=1, max_length=80)
    commune: str = Field(min_length=1, max_length=80)

    @field_validator(
        "prenom", "nom", "code_exploitation",
        "nom_exploitation", "commune"
    )
    @classmethod
    def verifier_texte(cls, valeur: str) -> str:
        valeur = valeur.strip()
        if not valeur:
            raise ValueError("Ce champ ne peut pas être vide")
        return valeur


class Connexion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    courriel: EmailStr = Field(max_length=120)
    mot_de_passe: str = Field(min_length=1, max_length=128, json_schema_extra={"writeOnly": True})


class UtilisateurPublic(BaseModel):
    id: int
    prenom: str
    nom: str
    courriel: EmailStr
    exploitation_id: int


class Jeton(BaseModel):
    access_token: str
    token_type: Literal["bearer"]
