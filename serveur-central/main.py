"""
Serveur central du réseau régional d'alertes — Jaden Konekté
Hébergé par l'enseignant. Implémente contrats/reseau-regional.openapi.yaml.

Lancement :
    pip install -r requirements.txt
    uvicorn main:app --host 0.0.0.0 --port 8080

Variables d'environnement :
    JADEN_DB     chemin de la base SQLite (défaut : central.db)
    JADEN_ADMIN  jeton administrateur pour DELETE /v1/plateformes/{id} (optionnel)
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Literal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import AnyHttpUrl, BaseModel, Field

DB_PATH = os.getenv("JADEN_DB", "central.db")
ADMIN_TOKEN = os.getenv("JADEN_ADMIN")
RETRY_DELAYS = [2, 8, 30]  # secondes, conformément au contrat
WEBHOOK_TIMEOUT = 5.0

Culture = Literal["tomate", "igname", "christophine", "banane", "piment", "laitue", "autre"]


# ---------------------------------------------------------------- modèles
class PlateformeIn(BaseModel):
    groupe: str = Field(min_length=2, max_length=40)
    nom: str = Field(max_length=80)
    membres: list[str] = Field(default_factory=list, max_length=6)
    url_base: AnyHttpUrl
    url_webhook: AnyHttpUrl
    secret: str = Field(min_length=16, max_length=128)


class Position(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class AlerteIn(BaseModel):
    type: Literal["maladie", "ravageur", "meteo", "secheresse"]
    culture: Culture
    maladie: str | None = Field(default=None, max_length=80)
    score: float | None = Field(default=None, ge=0, le=1)
    gravite: Literal["faible", "moyenne", "forte"]
    commune: str = Field(max_length=80)
    position: Position | None = None
    message: str | None = Field(default=None, max_length=500)
    observee_le: datetime


# ---------------------------------------------------------------- base
def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with db() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS plateforme (
              id TEXT PRIMARY KEY, groupe TEXT UNIQUE NOT NULL, nom TEXT NOT NULL,
              membres TEXT NOT NULL, url_base TEXT NOT NULL, url_webhook TEXT NOT NULL,
              secret TEXT NOT NULL, token_hash TEXT NOT NULL, inscrite_le TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS alerte (
              id TEXT PRIMARY KEY, emetteur TEXT NOT NULL REFERENCES plateforme(id),
              idem_key TEXT, contenu TEXT NOT NULL, recue_le TEXT NOT NULL,
              UNIQUE (emetteur, idem_key));
            CREATE TABLE IF NOT EXISTS livraison (
              alerte TEXT NOT NULL, plateforme TEXT NOT NULL, tentative INTEGER NOT NULL,
              statut TEXT NOT NULL, code_http INTEGER, erreur TEXT, horodatage TEXT NOT NULL);
            """
        )


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def plateforme_publique(r: sqlite3.Row) -> dict:
    return {
        "id": r["id"], "groupe": r["groupe"], "nom": r["nom"],
        "membres": json.loads(r["membres"]), "url_base": r["url_base"],
        "inscrite_le": r["inscrite_le"],
    }


def alerte_json(r: sqlite3.Row, emetteur: sqlite3.Row) -> dict:
    return {
        **json.loads(r["contenu"]),
        "id": r["id"],
        "emetteur": {"groupe": emetteur["groupe"], "nom": emetteur["nom"]},
        "recue_le": r["recue_le"],
    }


# ---------------------------------------------------------------- application
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.http = httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT)
    yield
    await app.state.http.aclose()


app = FastAPI(
    title="Réseau régional d'alertes Jaden Konekté",
    version="1.0.0",
    lifespan=lifespan,
)


def probleme(status: int, title: str, detail: str = "") -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={"type": "about:blank", "title": title, "status": status, "detail": detail},
    )


@app.exception_handler(HTTPException)
async def http_exc(_: Request, exc: HTTPException):
    return probleme(exc.status_code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_exc(_: Request, exc: RequestValidationError):
    champs = "; ".join(f"{'.'.join(map(str, e['loc']))} : {e['msg']}" for e in exc.errors())
    return probleme(422, "Données invalides", champs)


bearer = HTTPBearer(auto_error=False)


def plateforme_authentifiee(
    cred: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> sqlite3.Row:
    if cred is None:
        raise HTTPException(401, "Jeton manquant")
    with db() as con:
        r = con.execute(
            "SELECT * FROM plateforme WHERE token_hash = ?", (sha256(cred.credentials),)
        ).fetchone()
    if r is None:
        raise HTTPException(401, "Jeton invalide")
    return r


# ---------------------------------------------------------------- routes
@app.get("/v1/sante")
def sante():
    with db() as con:
        n_p = con.execute("SELECT count(*) FROM plateforme").fetchone()[0]
        n_a = con.execute("SELECT count(*) FROM alerte").fetchone()[0]
    return {"statut": "ok", "plateformes": n_p, "alertes": n_a}


@app.post("/v1/plateformes", status_code=201)
def inscrire(p: PlateformeIn):
    pid = "plt_" + secrets.token_hex(3)
    token = secrets.token_urlsafe(32)
    try:
        with db() as con:
            con.execute(
                "INSERT INTO plateforme VALUES (?,?,?,?,?,?,?,?,?)",
                (pid, p.groupe, p.nom, json.dumps(p.membres), str(p.url_base),
                 str(p.url_webhook), p.secret, sha256(token), now()),
            )
            r = con.execute("SELECT * FROM plateforme WHERE id = ?", (pid,)).fetchone()
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Le groupe « {p.groupe} » est déjà inscrit")
    return {**plateforme_publique(r), "token": token}


@app.get("/v1/plateformes")
def lister_plateformes():
    with db() as con:
        rows = con.execute("SELECT * FROM plateforme ORDER BY inscrite_le").fetchall()
    return [plateforme_publique(r) for r in rows]


@app.delete("/v1/plateformes/{pid}", status_code=204, include_in_schema=False)
def supprimer_plateforme(pid: str, authorization: Annotated[str | None, Header()] = None):
    if not ADMIN_TOKEN or authorization != f"Bearer {ADMIN_TOKEN}":
        raise HTTPException(403, "Réservé à l'administrateur")
    with db() as con:
        con.execute("DELETE FROM plateforme WHERE id = ?", (pid,))


_taches: set[asyncio.Task] = set()  # garde une référence aux diffusions en cours


@app.post("/v1/alertes", status_code=202)
async def publier(
    a: AlerteIn,
    emetteur: Annotated[sqlite3.Row, Depends(plateforme_authentifiee)],
    idempotency_key: Annotated[str | None, Header(max_length=64)] = None,
):
    with db() as con:
        if idempotency_key:
            deja = con.execute(
                "SELECT * FROM alerte WHERE emetteur = ? AND idem_key = ?",
                (emetteur["id"], idempotency_key),
            ).fetchone()
            if deja:
                return JSONResponse(status_code=200, content=alerte_json(deja, emetteur))
        aid = "alt_" + secrets.token_hex(4)
        contenu = a.model_dump(mode="json", exclude_none=True)
        con.execute(
            "INSERT INTO alerte VALUES (?,?,?,?,?)",
            (aid, emetteur["id"], idempotency_key, json.dumps(contenu), now()),
        )
        r = con.execute("SELECT * FROM alerte WHERE id = ?", (aid,)).fetchone()
        destinataires = con.execute(
            "SELECT * FROM plateforme WHERE id != ?", (emetteur["id"],)
        ).fetchall()
    corps = alerte_json(r, emetteur)
    for d in destinataires:  # une tâche par destinataire : un webhook lent ne bloque pas les autres
        t = asyncio.create_task(livrer(corps, dict(d)))
        _taches.add(t)
        t.add_done_callback(_taches.discard)
    return corps


@app.get("/v1/alertes")
def lister_alertes(
    depuis: datetime | None = None,
    commune: str | None = None,
    culture: Culture | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    sql, args = "SELECT a.*, p.groupe, p.nom FROM alerte a JOIN plateforme p ON p.id = a.emetteur WHERE 1=1", []
    if depuis:
        sql += " AND a.recue_le > ?"
        args.append(depuis.astimezone(timezone.utc).isoformat(timespec="seconds"))
    sql += " ORDER BY a.recue_le DESC LIMIT ?"
    args.append(limit * 4 if (commune or culture) else limit)
    with db() as con:
        rows = con.execute(sql, args).fetchall()
    res = []
    for r in rows:
        al = alerte_json(r, r)
        if commune and al["commune"].lower() != commune.lower():
            continue
        if culture and al["culture"] != culture:
            continue
        res.append(al)
    return res[:limit]


@app.get("/v1/alertes/{aid}/livraisons")
def livraisons(aid: str):
    with db() as con:
        if not con.execute("SELECT 1 FROM alerte WHERE id = ?", (aid,)).fetchone():
            raise HTTPException(404, "Alerte inconnue")
        rows = con.execute(
            """SELECT p.groupe, l.tentative, l.statut, l.code_http, l.erreur, l.horodatage
               FROM livraison l JOIN plateforme p ON p.id = l.plateforme
               WHERE l.alerte = ? ORDER BY l.horodatage""",
            (aid,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- diffusion
def signer(secret: str, corps: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), corps, hashlib.sha256).hexdigest()


def journaliser(aid: str, pid: str, tentative: int, statut: str, code: int | None, err: str | None):
    with db() as con:
        con.execute(
            "INSERT INTO livraison VALUES (?,?,?,?,?,?,?)",
            (aid, pid, tentative, statut, code, err, now()),
        )


async def livrer(alerte: dict, dest: dict) -> None:
    """Appelle le webhook d'une plateforme, avec reprises (2 s, 8 s, 30 s)."""
    corps = json.dumps(alerte, ensure_ascii=False).encode()
    entetes = {
        "Content-Type": "application/json",
        "X-Jaden-Signature": signer(dest["secret"], corps),
        "X-Jaden-Alerte": alerte["id"],
    }
    for tentative in range(1, len(RETRY_DELAYS) + 2):
        code, err = None, None
        try:
            r = await app.state.http.post(dest["url_webhook"], content=corps, headers=entetes)
            code = r.status_code
            if 200 <= code < 300:
                journaliser(alerte["id"], dest["id"], tentative, "succes", code, None)
                return
            err = f"HTTP {code}"
        except httpx.HTTPError as e:
            err = type(e).__name__
        journaliser(alerte["id"], dest["id"], tentative, "echec", code, err)
        if tentative <= len(RETRY_DELAYS):
            await asyncio.sleep(RETRY_DELAYS[tentative - 1])
