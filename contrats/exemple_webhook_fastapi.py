"""
Exemple minimal : recevoir les alertes du réseau régional dans VOTRE API FastAPI.
À intégrer (et adapter) dans votre projet : router, stockage, diffusion au tableau de bord.

Le secret doit être IDENTIQUE à celui déclaré lors de l'inscription (POST /v1/plateformes).
Ne le mettez pas dans le code : variable d'environnement JADEN_SECRET.
"""
import hashlib
import hmac
import json
import os

from fastapi import APIRouter, Header, HTTPException, Request, Response

SECRET = os.environ["JADEN_SECRET"].encode()
router = APIRouter()
_deja_recues: set[str] = set()  # en vrai : une table en base


@router.post("/webhooks/alertes", status_code=204)
async def alerte_recue(
    request: Request,
    x_jaden_signature: str = Header(...),
    x_jaden_alerte: str = Header(...),
):
    corps = await request.body()  # corps BRUT : ne pas re-sérialiser avant de vérifier
    attendu = "sha256=" + hmac.new(SECRET, corps, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(attendu, x_jaden_signature):
        raise HTTPException(401, "Signature invalide")

    if x_jaden_alerte in _deja_recues:  # le serveur central peut réessayer : ignorer les doublons
        return Response(status_code=204)
    _deja_recues.add(x_jaden_alerte)

    alerte = json.loads(corps)
    # TODO : enregistrer l'alerte, la pousser au tableau de bord (WebSocket / SSE),
    #        éventuellement déclencher une règle (ex. inspection des parcelles de même culture).
    print(f"[alerte] {alerte['emetteur']['groupe']} : {alerte['culture']} / "
          f"{alerte.get('maladie', alerte['type'])} à {alerte['commune']}")
    return Response(status_code=204)
