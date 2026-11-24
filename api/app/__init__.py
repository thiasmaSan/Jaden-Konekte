
from pydantic import BaseModel, EmailStr, Field, field_validator


class Inscription(BaseModel):
    prenom: str = Field(min_length=1, max_length=40)
    nom: str = Field(min_length=1, max_length=40)
    courriel: EmailStr
    mot_de_passe: str = Field(min_length=12, max_length=128)
    code_exploitation: str = Field(min_length=1, max_length=30)
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
    courriel: EmailStr
    mot_de_passe: str


class UtilisateurPublic(BaseModel):
    id: int
    prenom: str
    nom: str
    courriel: EmailStr
    exploitation_id: int


class Jeton(BaseModel):
    access_token: str
    token_type: str = "bearer"
