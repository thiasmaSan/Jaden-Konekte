
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt import InvalidTokenError

from .jwt import decoder_jeton

bearer = HTTPBearer(auto_error=False, scheme_name="bearerAuth")


def utilisateur_connecte(
    credentials: HTTPAuthorizationCredentials = Depends(bearer)
) -> int:
    erreur = HTTPException(
        status_code=401,
        detail="Authentification requise",
        headers={"WWW-Authenticate": "Bearer"}
    )

    if credentials is None:
        raise erreur

    try:
        donnees = decoder_jeton(credentials.credentials)
        utilisateur_id = int(donnees["sub"])

        if utilisateur_id <= 0:
            raise erreur

        return utilisateur_id

    except (InvalidTokenError, KeyError, ValueError, TypeError):
        raise erreur
