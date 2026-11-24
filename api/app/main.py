from .routers.auth import router as auth_router
from fastapi import FastAPI, HTTPException
from .database import get_connection
from .errors import installer_gestion_erreurs, reponses_erreurs
from .schemas.systeme import Sante, SanteBase
from .routers.parcelles import router as parcelles_router
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .routers.temps_reel import router as temps_reel_router
import asyncio
from contextlib import asynccontextmanager, suppress
from .services.arrosage import planifier_arrosage
from .routers.vannes import router as vannes_router
from .services.mqtt_vannes import (
    demarrer_mqtt,
    arreter_mqtt,
)
from .routers.irrigation import router as irrigation_router
from .routers.diagnostics import router as diagnostics_router
from .routers.assistant import router as assistant_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    demarrer_mqtt()
    planificateur = asyncio.create_task(planifier_arrosage())

    try:
        yield
    finally:
        planificateur.cancel()
        with suppress(asyncio.CancelledError):
            await planificateur
        arreter_mqtt()


app = FastAPI(
    title="Jaden Konekté API",
    version="1.0.0",
    description="API de suivi des exploitations agricoles",
    lifespan=lifespan,
)
app.include_router(vannes_router)
app.include_router(irrigation_router)
app.include_router(diagnostics_router)
app.include_router(assistant_router)
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app.mount(
    "/static",
    StaticFiles(directory=FRONTEND_DIR),
    name="static"
)


@app.get("/dashboard", include_in_schema=False)
def afficher_dashboard():
    return FileResponse(FRONTEND_DIR / "index.html")
app.include_router(auth_router)
app.include_router(parcelles_router)
app.include_router(temps_reel_router)

installer_gestion_erreurs(app)


@app.get("/api/v1/sante", tags=["Système"], response_model=Sante, operation_id="verifierSante")
def verifier_sante():
    return {"statut": "ok", "service": "Jaden Konekté"}


@app.get("/api/v1/sante/database", tags=["Système"], response_model=SanteBase,
         operation_id="verifierBase", responses=reponses_erreurs(500, 503))
def verifier_base():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return {"statut": "ok", "database": "connectee"}
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Base de données indisponible"
        )


