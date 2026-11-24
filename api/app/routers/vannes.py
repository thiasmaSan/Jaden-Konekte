
from uuid import uuid4

from fastapi import (
    APIRouter, Depends, HTTPException, Path
)
from psycopg.rows import dict_row

from ..errors import reponses_erreurs
from ..database import get_connection
from ..security.dependencies import utilisateur_connecte
from ..schemas.vannes import (
    NouvelleCommandeVanne,
    CommandeVanne,
)
from ..services.mqtt_vannes import publier_commande

router = APIRouter(
    prefix="/api/v1/parcelles",
    tags=["Vannes"],
)


def autoriser_commande(parcelle_id, utilisateur_id):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    p.id,
                    p.code,
                    x.code AS exploitation_code,
                    m.role
                FROM parcelle p
                JOIN exploitation x
                  ON x.id = p.exploitation
                JOIN membre m
                  ON m.exploitation = x.id
                WHERE p.id = %s
                  AND m.utilisateur = %s
                """,
                (parcelle_id, utilisateur_id),
            )

            parcelle = cur.fetchone()

    if parcelle is None:
        raise HTTPException(
            404, "Parcelle introuvable ou inaccessible"
        )

    if parcelle["role"] not in ("exploitant", "admin"):
        raise HTTPException(
            403, "Commande interdite pour ce rôle"
        )

    return parcelle


@router.post(
    "/{id}/vanne/commandes",
    status_code=202,
    response_model=CommandeVanne,
    operation_id="commanderVanne",
    responses=reponses_erreurs(401, 403, 404, 422, 500, 503),
)
def commander_vanne(
    donnees: NouvelleCommandeVanne,
    id: int = Path(ge=1),
    utilisateur_id: int = Depends(utilisateur_connecte),
):
    parcelle = autoriser_commande(id, utilisateur_id)
    commande_id = f"cmd-{uuid4().hex}"

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id
                FROM equipement
                WHERE parcelle = %s
                  AND type = 'vanne'
                ORDER BY id
                LIMIT 1
                """,
                (id,),
            )
            equipement = cur.fetchone()

            if equipement is None:
                raise HTTPException(
                    404,
                    "Aucune vanne enregistrée"
                )

            cur.execute(
                """
                INSERT INTO commande (
                    id, equipement, action,
                    duree_s, origine, auteur, statut
                )
                VALUES (
                    %s, %s, %s, %s,
                    'manuelle', %s, 'envoyee'
                )
                RETURNING
                    id, equipement, action,
                    duree_s, origine, statut, cree_le
                """,
                (
                    commande_id,
                    equipement["id"],
                    donnees.action,
                    donnees.duree_s,
                    utilisateur_id,
                ),
            )
            commande = cur.fetchone()

    topic = (
        f"jaden/{parcelle['exploitation_code']}"
        f"/{parcelle['code']}/vanne/cmd"
    )

    message = {
        "id": commande_id,
        "action": donnees.action,
    }

    if donnees.action == "ouvrir":
        message["duree_s"] = donnees.duree_s

    try:
        publier_commande(topic, message)
    except RuntimeError:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE commande
                    SET statut = 'echec'
                    WHERE id = %s
                      AND statut = 'envoyee'
                    """,
                    (commande_id,),
                )

        raise HTTPException(
            503,
            "Publication MQTT non confirmée"
        )

    return commande


@router.get(
    "/{id}/vanne/commandes/{commande_id}",
    response_model=CommandeVanne,
    operation_id="consulterCommandeVanne",
    responses=reponses_erreurs(401, 403, 404, 422, 500, 503),
)
def consulter_commande(
    id: int = Path(ge=1),
    commande_id: str = Path(min_length=1),
    utilisateur_id: int = Depends(utilisateur_connecte),
):
    autoriser_commande(id, utilisateur_id)

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    c.id, c.equipement, c.action,
                    c.duree_s, c.origine,
                    c.statut, c.cree_le
                FROM commande c
                JOIN equipement e
                  ON e.id = c.equipement
                WHERE c.id = %s
                  AND e.parcelle = %s
                """,
                (commande_id, id),
            )

            commande = cur.fetchone()

    if commande is None:
        raise HTTPException(
            404, "Commande introuvable"
        )

    return commande
