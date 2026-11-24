
import os
from datetime import datetime
from typing import Optional

import httpx
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Path,
    Query,
    UploadFile,
)
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from psycopg.rows import dict_row

from ..errors import reponses_erreurs
from ..database import get_connection
from ..routers.parcelles import parcelle_accessible
from ..security.dependencies import utilisateur_connecte

router = APIRouter(
    prefix="/api/v1/parcelles",
    tags=["Diagnostics"],
)

CNN_URL = os.getenv(
    "CNN_URL",
    "http://inference-cnn:8001",
).rstrip("/")

TAILLE_MAX = 5 * 1024 * 1024


class Diagnostic(BaseModel):
    id: int
    parcelle: int
    auteur: Optional[int]
    image_url: str
    statut: str
    classe: Optional[str]
    score: Optional[float]
    modele: Optional[str]
    confirme: Optional[bool]
    cree_le: datetime
    termine_le: Optional[datetime]


@router.post(
    "/{id}/diagnostics", status_code=201, response_model=Diagnostic,
    operation_id="creerDiagnostic",
    responses=reponses_erreurs(401, 404, 413, 415, 422, 500, 502, 503),
)
async def creer_diagnostic(
    id: int = Path(ge=1),
    image: UploadFile = File(...),
    parcelle: dict = Depends(parcelle_accessible),
    utilisateur_id: int = Depends(utilisateur_connecte),
):
    if image.content_type not in (
        "image/jpeg",
        "image/png",
    ):
        raise HTTPException(
            status_code=415,
            detail="Format accepté : JPEG ou PNG",
        )

    contenu = await image.read(TAILLE_MAX + 1)

    if len(contenu) > TAILLE_MAX:
        raise HTTPException(
            status_code=413,
            detail="Image supérieure à 5 Mo",
        )

    if not contenu:
        raise HTTPException(
            status_code=422,
            detail="L'image est vide",
        )

    try:
        async with httpx.AsyncClient(
            timeout=35.0
        ) as client:
            reponse = await client.post(
                f"{CNN_URL}/predictions",
                files={
                    "image": (
                        image.filename or "image.jpg",
                        contenu,
                        image.content_type,
                    )
                },
            )

    except httpx.RequestError:
        raise HTTPException(
            status_code=503,
            detail="Service CNN indisponible",
        )

    if reponse.status_code in (413, 415, 422):
        raise HTTPException(reponse.status_code, "Image illisible ou non prise en charge")

    if reponse.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Le service CNN a rejeté l'analyse",
        )

    try:
        resultat = reponse.json()

        classe = str(resultat["classe"])
        confiance = float(resultat["confiance"])
        modele = str(resultat["version_modele"])

        if not 0 <= confiance <= 1:
            raise ValueError("Confiance invalide")

    except (ValueError, KeyError, TypeError):
        raise HTTPException(
            status_code=502,
            detail="Réponse CNN invalide",
        )

    return await run_in_threadpool(enregistrer_diagnostic, id, utilisateur_id, classe, confiance, modele)


def enregistrer_diagnostic(id, utilisateur_id, classe, confiance, modele):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:

            # Vérification de l'accès avant l'écriture.
            cur.execute(
                """
                SELECT 1
                FROM parcelle p
                JOIN membre m
                  ON m.exploitation = p.exploitation
                WHERE p.id = %s
                  AND m.utilisateur = %s
                FOR SHARE OF p, m
                """,
                (id, utilisateur_id),
            )

            if cur.fetchone() is None:
                raise HTTPException(
                    status_code=404,
                    detail="Parcelle inaccessible",
                )

            cur.execute(
                """
                INSERT INTO diagnostic (
                    parcelle,
                    auteur,
                    image_url,
                    statut,
                    classe,
                    score,
                    modele,
                    termine_le
                )
                VALUES (
                    %s, %s, %s, 'termine',
                    %s, %s, %s, now()
                )
                RETURNING *
                """,
                (
                    id,
                    utilisateur_id,
                    "non_conservee",
                    classe,
                    confiance,
                    modele,
                ),
            )

            diagnostic = cur.fetchone()

    return diagnostic


@router.get(
    "/{id}/diagnostics", response_model=list[Diagnostic],
    operation_id="listerDiagnostics", responses=reponses_erreurs(401, 404, 422, 500, 503),
)
def lister_diagnostics(
    id: int = Path(ge=1),
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    parcelle: dict = Depends(parcelle_accessible),
    utilisateur_id: int = Depends(utilisateur_connecte),
):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT d.*
                FROM diagnostic d
                JOIN parcelle p
                  ON p.id = d.parcelle
                JOIN membre m
                  ON m.exploitation = p.exploitation
                WHERE d.parcelle = %s
                  AND m.utilisateur = %s
                ORDER BY d.cree_le DESC, d.id DESC
                LIMIT %s OFFSET %s
                """,
                (id, utilisateur_id, limit, offset),
            )

            return cur.fetchall()
