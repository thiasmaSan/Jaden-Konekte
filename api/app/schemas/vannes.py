from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NouvelleCommandeVanne(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["ouvrir", "fermer"]
    duree_s: Optional[int] = Field(
        default=None, ge=10, le=3600
    )

    @model_validator(mode="after")
    def verifier_duree(self):
        if self.action == "ouvrir":
            if self.duree_s is None:
                raise ValueError(
                    "La durée est obligatoire pour ouvrir"
                )
        elif self.duree_s is not None:
            raise ValueError(
                "La fermeture ne prend pas de durée"
            )
        return self


class CommandeVanne(BaseModel):
    id: str
    equipement: int
    action: str
    duree_s: Optional[int]
    origine: str
    statut: str
    cree_le: datetime
