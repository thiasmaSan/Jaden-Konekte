from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from typing import List, Literal
from ..schemas.tableau_de_bord import TableauDeBord
from ..services.tableau_de_bord import recuperer_tableau_de_bord

from psycopg import errors
from psycopg import sql
from psycopg.rows import dict_row

from ..database import get_connection
from ..security.dependencies import utilisateur_connecte
from ..schemas.parcelles import CreationParcelle, ModificationParcelle, Parcelle, Mesure, AgregatMesure
from ..errors import reponses_erreurs

router = APIRouter(prefix="/api/v1/parcelles", tags=["Parcelles"])

CHAMPS_PARCELLE = """
    p.id, p.exploitation, p.code, p.nom, p.culture,
    p.seuil_sec::float AS seuil_sec, p.surface_m2::float AS surface_m2
"""


ERREURS_CREATION = reponses_erreurs(401, 403, 404, 409, 422, 500, 503)


@router.post("", status_code=201, response_model=Parcelle,
             operation_id="creerParcelle", responses={
                 **ERREURS_CREATION,
                 201: {"headers": {"Location": {"schema": {"type": "string"}}}},
             })
def creer_parcelle(donnees: CreationParcelle, response: Response,
                   utilisateur_id: int = Depends(utilisateur_connecte)):
    try:
        with get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # Le verrou conserve l'appartenance et le rôle jusqu'à la fin de la transaction.
                cur.execute(
                    """SELECT role FROM membre
                    WHERE utilisateur = %s AND exploitation = %s FOR SHARE""",
                    (utilisateur_id, donnees.exploitation),
                )
                membre = cur.fetchone()
                if membre is None:
                    raise HTTPException(404, "Exploitation introuvable ou inaccessible")
                if membre["role"] not in ("exploitant", "admin"):
                    raise HTTPException(403, "Ce rôle ne permet pas de créer une parcelle")
                cur.execute(
                    """INSERT INTO parcelle AS p
                    (exploitation, code, nom, culture, surface_m2, seuil_sec)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING """ + CHAMPS_PARCELLE,
                    (donnees.exploitation, donnees.code, donnees.nom, donnees.culture,
                     donnees.surface_m2, donnees.seuil_sec),
                )
                parcelle = cur.fetchone()
    except errors.UniqueViolation:
        raise HTTPException(409, "Code de parcelle déjà utilisé dans cette exploitation")
    response.headers["Location"] = f"/api/v1/parcelles/{parcelle['id']}"
    return parcelle


def parcelle_accessible(id: int = Path(ge=1),
                        utilisateur_id: int = Depends(utilisateur_connecte)):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""SELECT {CHAMPS_PARCELLE}
                FROM parcelle AS p
                JOIN membre AS m ON m.exploitation = p.exploitation
                WHERE p.id = %s AND m.utilisateur = %s""",
                (id, utilisateur_id),
            )
            parcelle = cur.fetchone()
    if parcelle is None:
        raise HTTPException(404, "Parcelle introuvable ou inaccessible")
    return parcelle


@router.get("", response_model=List[Parcelle], operation_id="listerParcelles",
            responses=reponses_erreurs(401, 422, 500, 503))
def lister_parcelles(limit: int = Query(20, ge=1, le=100),
                    offset: int = Query(0, ge=0),
                    utilisateur_id: int = Depends(utilisateur_connecte)):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""SELECT {CHAMPS_PARCELLE}
                FROM parcelle AS p
                JOIN membre AS m ON m.exploitation = p.exploitation
                WHERE m.utilisateur = %s
                ORDER BY p.id LIMIT %s OFFSET %s""",
                (utilisateur_id, limit, offset),
            )
            return cur.fetchall()


@router.get("/{id}", response_model=Parcelle, operation_id="obtenirParcelle",
            responses=reponses_erreurs(401, 404, 422, 500, 503))
def obtenir_parcelle(parcelle: dict = Depends(parcelle_accessible)):
    return parcelle


@router.patch("/{id}", response_model=Parcelle, operation_id="modifierParcelle",
              responses={code: valeur for code, valeur in ERREURS_CREATION.items() if code != 409})
def modifier_parcelle(donnees: ModificationParcelle, id: int = Path(ge=1),
                       utilisateur_id: int = Depends(utilisateur_connecte)):
    changements = donnees.model_dump(exclude_unset=True)
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT m.role FROM parcelle AS p
                JOIN membre AS m ON m.exploitation = p.exploitation
                WHERE p.id = %s AND m.utilisateur = %s
                FOR UPDATE OF p FOR SHARE OF m""",
                (id, utilisateur_id),
            )
            membre = cur.fetchone()
            if membre is None:
                raise HTTPException(404, "Parcelle introuvable ou inaccessible")
            if membre["role"] not in ("exploitant", "admin"):
                raise HTTPException(403, "Ce rôle ne permet pas de modifier une parcelle")
            # Identifiants SQL échappés ; valeurs liées séparément, champs limités par Pydantic.
            affectations = sql.SQL(", ").join(
                sql.SQL("{} = %s").format(sql.Identifier(champ)) for champ in changements
            )
            cur.execute(
                sql.SQL("UPDATE parcelle AS p SET {} WHERE p.id = %s RETURNING ").format(affectations)
                + sql.SQL(CHAMPS_PARCELLE),
                (*changements.values(), id),
            )
            return cur.fetchone()


@router.get("/{id}/mesures", tags=["Mesures"], response_model=List[Mesure],
            operation_id="listerMesures", responses=reponses_erreurs(401, 404, 422, 500, 503))
def lister_mesures(limit: int = Query(100, ge=1, le=1000),
                   offset: int = Query(0, ge=0),
                   parcelle: dict = Depends(parcelle_accessible)):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT m.ts, m.capteur, m.valeur, m.valide
                FROM mesure AS m
                JOIN capteur AS c ON c.id = m.capteur
                WHERE c.parcelle = %s
                ORDER BY m.ts DESC, m.capteur
                LIMIT %s OFFSET %s""",
                (parcelle["id"], limit, offset),
            )
            return cur.fetchall()


@router.get("/{id}/mesures/agregats", tags=["Mesures"], response_model=List[AgregatMesure],
            operation_id="agregerMesures", responses=reponses_erreurs(401, 404, 422, 500, 503))
def agreger_mesures(intervalle: Literal["heure", "jour"] = "heure",
                    jours: int = Query(1, ge=1, le=7),
                    parcelle: dict = Depends(parcelle_accessible)):
    duree = {"heure": "1 hour", "jour": "1 day"}[intervalle]
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT time_bucket(%s::interval, m.ts) AS ts, m.capteur,
                avg(m.valeur) AS moyenne, min(m.valeur) AS minimum,
                max(m.valeur) AS maximum, count(*) AS nombre
                FROM mesure AS m JOIN capteur AS c ON c.id = m.capteur
                WHERE c.parcelle = %s AND m.valide = true
                  AND m.ts >= now() - make_interval(days => %s) AND m.ts <= now()
                GROUP BY 1, m.capteur ORDER BY 1, m.capteur""",
                (duree, parcelle["id"], jours),
            )
            return cur.fetchall()


ERREURS_SUPPRESSION = {
    **ERREURS_CREATION,
    404: {**ERREURS_CREATION[404], "description": "Parcelle introuvable ou inaccessible"},
    409: {**ERREURS_CREATION[409], "description": "La parcelle possède des données liées"},
}


@router.delete("/{id}", status_code=204, response_class=Response,
               operation_id="supprimerParcelle", responses=ERREURS_SUPPRESSION)
def supprimer_parcelle(id: int = Path(ge=1),
                        utilisateur_id: int = Depends(utilisateur_connecte)):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # Le verrou empêche l'ajout concurrent de références à cette parcelle
            # pendant la vérification et la suppression (verrous des clés étrangères).
            cur.execute(
                """SELECT m.role FROM parcelle AS p
                JOIN membre AS m ON m.exploitation = p.exploitation
                WHERE p.id = %s AND m.utilisateur = %s
                FOR UPDATE OF p FOR SHARE OF m""",
                (id, utilisateur_id),
            )
            membre = cur.fetchone()
            if membre is None:
                raise HTTPException(404, "Parcelle introuvable ou inaccessible")
            if membre["role"] not in ("exploitant", "admin"):
                raise HTTPException(403, "Ce rôle ne permet pas de supprimer une parcelle")
            cur.execute(
                """SELECT
                EXISTS (SELECT 1 FROM capteur WHERE parcelle = %s) AS capteurs,
                EXISTS (SELECT 1 FROM equipement WHERE parcelle = %s) AS equipements,
                EXISTS (SELECT 1 FROM regle WHERE parcelle = %s) AS regles,
                EXISTS (SELECT 1 FROM diagnostic WHERE parcelle = %s) AS diagnostics""",
                (id, id, id, id),
            )
            if any(cur.fetchone().values()):
                raise HTTPException(409, "Suppression refusée : la parcelle possède des données liées")
            cur.execute("DELETE FROM parcelle WHERE id = %s", (id,))
    return Response(status_code=204)


@router.get(
    "/{id}/tableau-de-bord",
    tags=["Tableau de bord"],
    response_model=TableauDeBord,
    operation_id="obtenirTableauDeBord",
    responses=reponses_erreurs(
        401, 404, 422, 500, 503
    ),
)
def obtenir_tableau_de_bord(
    parcelle: dict = Depends(parcelle_accessible),
):
    """
    Retourne l'état actuel d'une parcelle :
    - informations générales ;
    - dernières mesures valides ;
    - disponibilité estimée des capteurs ;
    - états connus des vannes.
    """

    return recuperer_tableau_de_bord(parcelle)

