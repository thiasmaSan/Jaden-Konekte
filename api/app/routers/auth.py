
from fastapi import APIRouter, HTTPException, status
from psycopg import errors
from psycopg.rows import dict_row

from ..database import get_connection
from ..errors import reponses_erreurs
from ..schemas.auth import (
    Inscription,
    Connexion,
    UtilisateurPublic,
    Jeton
)
from ..security.jwt import (
    hacher_mot_de_passe,
    verifier_mot_de_passe,
    creer_jeton
)


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentification"]
)


@router.post(
    "/inscription",
    status_code=status.HTTP_201_CREATED,
    response_model=UtilisateurPublic,
    operation_id="inscrireUtilisateur",
    responses=reponses_erreurs(409, 422, 500, 503)
)
def inscription(donnees: Inscription):
    empreinte = hacher_mot_de_passe(donnees.mot_de_passe)

    try:
        with get_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:

                cur.execute(
                    """
                    INSERT INTO utilisateur
                        (prenom, nom, courriel, mot_de_passe)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, prenom, nom, courriel
                    """,
                    (
                        donnees.prenom,
                        donnees.nom,
                        str(donnees.courriel).lower(),
                        empreinte
                    )
                )
                utilisateur = cur.fetchone()

                cur.execute(
                    """
                    INSERT INTO exploitation
                        (code, nom, commune)
                    VALUES (%s, %s, %s)
                    RETURNING id
                    """,
                    (
                        donnees.code_exploitation,
                        donnees.nom_exploitation,
                        donnees.commune
                    )
                )
                exploitation = cur.fetchone()

                cur.execute(
                    """
                    INSERT INTO membre
                        (utilisateur, exploitation, role)
                    VALUES (%s, %s, %s)
                    """,
                    (
                        utilisateur["id"],
                        exploitation["id"],
                        "exploitant"
                    )
                )

                return {
                    **utilisateur,
                    "exploitation_id": exploitation["id"]
                }

    except errors.UniqueViolation:
        raise HTTPException(
            status_code=409,
            detail="Courriel ou code d'exploitation déjà utilisé"
        )


@router.post(
    "/connexion",
    response_model=Jeton,
    operation_id="connecterUtilisateur",
    responses=reponses_erreurs(401, 422, 500, 503)
)
def connexion(donnees: Connexion):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, mot_de_passe
                FROM utilisateur
                WHERE lower(courriel) = %s
                """,
                (str(donnees.courriel).lower(),)
            )
            utilisateur = cur.fetchone()

    if utilisateur is None:
        raise HTTPException(
            status_code=401,
            detail="Identifiants incorrects",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if not verifier_mot_de_passe(
        donnees.mot_de_passe,
        utilisateur["mot_de_passe"]
    ):
        raise HTTPException(
            status_code=401,
            detail="Identifiants incorrects",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = creer_jeton(utilisateur["id"])

    return {
        "access_token": token,
        "token_type": "bearer"
    }
