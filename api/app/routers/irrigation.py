
from fastapi import (
    APIRouter,
    Depends,
    Query,
    HTTPException,
)

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..database import get_connection
from ..security.dependencies import utilisateur_connecte
from ..errors import reponses_erreurs
from ..routers.parcelles import (
    parcelle_accessible,
)
from ..schemas.irrigation import (
    RecommandationIrrigation,
    ConfigurationArrosage,
)
from ..services.meteo import (
    MeteoIndisponible,
    recuperer_meteo,
)
from ..services.irrigation import (
    analyser_irrigation,
)


router = APIRouter(
    prefix="/api/v1/parcelles",
    tags=["Irrigation"],
)


@router.get(
    "/{id}/irrigation/recommandation",
    response_model=RecommandationIrrigation,
    operation_id="recommanderIrrigation",
    responses=reponses_erreurs(401, 404, 422, 500, 503),
)
def recommander_irrigation(
    latitude: float = Query(
        ge=-90, le=90
    ),
    longitude: float = Query(
        ge=-180, le=180
    ),
    parcelle: dict = Depends(
        parcelle_accessible
    ),
):
    try:
        meteo = recuperer_meteo(
            latitude,
            longitude,
        )

    except MeteoIndisponible:
        meteo = None

    return analyser_irrigation(
        parcelle,
        meteo,
    )


@router.get(
    "/{id}/regles/automatique",
    response_model=ConfigurationArrosage,
    operation_id="consulterRegleAutomatique",
    responses=reponses_erreurs(401, 404, 422, 500, 503),
)
def consulter_regle(parcelle: dict = Depends(parcelle_accessible)):
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT active, condition, action FROM regle WHERE parcelle = %s AND nom = 'Automatique'",
            (parcelle["id"],),
        )
        regle = cur.fetchone()
    if regle is None:
        raise HTTPException(404, "Règle automatique non configurée")
    return {**regle["condition"], **regle["action"], "active": regle["active"]}


@router.put(
    "/{id}/regles/automatique",
    response_model=ConfigurationArrosage,
    operation_id="configurerRegleAutomatique",
    responses=reponses_erreurs(401, 403, 404, 422, 500, 503),
)
def configurer_regle(
    donnees: ConfigurationArrosage,
    parcelle: dict = Depends(parcelle_accessible),
    utilisateur_id: int = Depends(utilisateur_connecte),
):
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT m.role FROM parcelle p JOIN membre m ON m.exploitation = p.exploitation
               WHERE p.id = %s AND m.utilisateur = %s FOR UPDATE OF p FOR SHARE OF m""",
            (parcelle["id"], utilisateur_id),
        )
        membre = cur.fetchone()
        if membre is None:
            raise HTTPException(404, "Parcelle inaccessible")
        if membre["role"] not in ("admin", "exploitant"):
            raise HTTPException(403, "Modification de règle interdite")
        condition = donnees.model_dump(exclude={"active", "duree_s"})
        action = {"duree_s": donnees.duree_s}
        cur.execute(
            """UPDATE regle SET condition = %s, action = %s, active = %s
               WHERE parcelle = %s AND nom = 'Automatique'""",
            (Jsonb(condition), Jsonb(action), donnees.active, parcelle["id"]),
        )
        if cur.rowcount == 0:
            cur.execute(
                """INSERT INTO regle (parcelle, nom, condition, action, active)
                   VALUES (%s, 'Automatique', %s, %s, %s)""",
                (parcelle["id"], Jsonb(condition), Jsonb(action), donnees.active),
            )
    return donnees
