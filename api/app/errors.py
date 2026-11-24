from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from psycopg import OperationalError, InterfaceError

from .schemas.systeme import Probleme


def reponses_erreurs(*codes):
    """Décrit le format réellement renvoyé, y compris pour les validations 422."""
    return {
        code: {
            "description": HTTPStatus(code).phrase,
            "content": {"application/problem+json": {"schema": Probleme.model_json_schema()}},
        }
        for code in codes
    }


def installer_gestion_erreurs(app: FastAPI):
    @app.exception_handler(OperationalError)
    @app.exception_handler(InterfaceError)
    async def erreur_base(request: Request, exc: Exception):
        return await erreur_http(request, HTTPException(503, "Base de données indisponible"))

    @app.exception_handler(Exception)
    async def erreur_interne(request: Request, exc: Exception):
        # Ne jamais renvoyer de requête SQL, secret ou trace technique au client.
        return await erreur_http(request, HTTPException(500, "Erreur interne du serveur"))

    @app.exception_handler(HTTPException)
    async def erreur_http(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            media_type="application/problem+json",
            headers=exc.headers,
            content={
                "type": "about:blank",
                "title": HTTPStatus(exc.status_code).phrase,
                "status": exc.status_code,
                "detail": str(exc.detail),
                "instance": request.url.path,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def erreur_validation(request: Request, exc: RequestValidationError):
        detail = "; ".join(
            f"{'.'.join(map(str, erreur['loc']))} : {erreur['msg']}"
            for erreur in exc.errors()
        )
        return JSONResponse(
            status_code=422,
            media_type="application/problem+json",
            content={
                "type": "about:blank",
                "title": "Unprocessable Entity",
                "status": 422,
                "detail": detail,
                "instance": request.url.path,
            },
        )
