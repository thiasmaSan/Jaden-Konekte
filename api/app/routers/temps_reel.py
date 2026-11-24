
import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from ..errors import reponses_erreurs
from ..routers.parcelles import parcelle_accessible
from ..services.tableau_de_bord import recuperer_tableau_de_bord


router = APIRouter(
    prefix="/api/v1/parcelles",
    tags=["Temps réel"],
)

INTERVALLE_S = 5
HEARTBEAT_S = 15


def encoder_evenement(nom: str, donnees: dict) -> str:
    contenu = json.dumps(
        jsonable_encoder(donnees),
        ensure_ascii=False,
    )

    return f"event: {nom}\ndata: {contenu}\n\n"


def signature_donnees(tableau: dict) -> str:
    """
    Compare les données métier sans actualise_le,
    qui change à chaque consultation.
    """
    donnees = {
        cle: valeur
        for cle, valeur in tableau.items()
        if cle != "actualise_le"
    }

    return json.dumps(
        jsonable_encoder(donnees),
        sort_keys=True,
        ensure_ascii=False,
    )


@router.get(
    "/{id}/evenements",
    operation_id="suivreEvenementsParcelle",
    response_class=StreamingResponse,
    responses={
        200: {"description": "Flux SSE", "content": {"text/event-stream": {"schema": {"type": "string"}}}},
        **reponses_erreurs(401, 404, 422, 500, 503),
    },
)
async def suivre_evenements_parcelle(
    request: Request,
    parcelle: dict = Depends(parcelle_accessible),
):
    async def produire_evenements():
        signature_precedente = None
        dernier_envoi = datetime.now(timezone.utc)

        while not await request.is_disconnected():
            try:
                # La lecture SQL est synchrone.
                # to_thread évite de bloquer
                # la boucle événementielle FastAPI.
                tableau = await asyncio.to_thread(
                    recuperer_tableau_de_bord,
                    parcelle,
                )

                signature = signature_donnees(tableau)

                if signature != signature_precedente:
                    yield encoder_evenement(
                        "tableau_de_bord",
                        tableau,
                    )

                    signature_precedente = signature
                    dernier_envoi = datetime.now(
                        timezone.utc
                    )

                else:
                    maintenant = datetime.now(
                        timezone.utc
                    )

                    if (
                        maintenant - dernier_envoi
                    ).total_seconds() >= HEARTBEAT_S:
                        yield ": heartbeat\n\n"
                        dernier_envoi = maintenant

            except asyncio.CancelledError:
                raise

            except Exception:
                # Une erreur après l'ouverture du flux
                # ne peut plus modifier le code HTTP.
                yield encoder_evenement(
                    "erreur",
                    {
                        "message":
                            "Flux temporairement indisponible"
                    },
                )
                return

            await asyncio.sleep(INTERVALLE_S)

    return StreamingResponse(
        produire_evenements(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
