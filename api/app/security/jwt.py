
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from ..config import settings


password_hash = PasswordHash.recommended()


def hacher_mot_de_passe(mot_de_passe: str) -> str:
    return password_hash.hash(mot_de_passe)


def verifier_mot_de_passe(
    mot_de_passe: str,
    empreinte: str
) -> bool:
    return password_hash.verify(mot_de_passe, empreinte)


def creer_jeton(utilisateur_id: int) -> str:
    maintenant = datetime.now(timezone.utc)

    donnees = {
        "sub": str(utilisateur_id),
        "iat": maintenant,
        "exp": maintenant + timedelta(
            minutes=settings.jwt_expiration_minutes
        )
    }

    return jwt.encode(
        donnees,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm
    )


def decoder_jeton(token: str) -> dict:
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["sub", "iat", "exp"]}
    )
