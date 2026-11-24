
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from .parcelles import Parcelle


class DerniereMesure(BaseModel):
    valeur: float
    ts: datetime


class EtatCapteur(BaseModel):
    id: int
    type: str
    grandeur: str
    unite: str
    actif: bool
    en_ligne: bool
    derniere_mesure: Optional[DerniereMesure] = None


class EtatVanne(BaseModel):
    id: int
    type: str
    etat: str
    maj_le: Optional[datetime] = None


class ResumeCapteurs(BaseModel):
    total: int
    actifs: int
    en_ligne: int


class TableauDeBord(BaseModel):
    parcelle: Parcelle
    capteurs: List[EtatCapteur]
    resume_capteurs: ResumeCapteurs
    vannes: List[EtatVanne]
    actualise_le: datetime
