from pydantic import BaseModel, Field


class Probleme(BaseModel):
    type: str = Field(json_schema_extra={"format": "uri-reference"})
    title: str
    status: int
    detail: str = ""
    instance: str = ""


class Sante(BaseModel):
    statut: str
    service: str


class SanteBase(BaseModel):
    statut: str
    database: str
