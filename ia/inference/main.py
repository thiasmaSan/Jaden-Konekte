
import io
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

MODEL_DIR = Path(os.getenv("MODEL_DIR", "/modeles"))
MODEL_VERSION = os.getenv("MODEL_VERSION", "mobilenetv3-small-v1")
MAX_BYTES = 5 * 1024 * 1024

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

Image.MAX_IMAGE_PIXELS = 20_000_000

session = None
classes = None
libelles = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global session, classes, libelles

    classes = json.loads(
        (MODEL_DIR / "classes.json").read_text(encoding="utf-8")
    )

    libelles = json.loads((MODEL_DIR / "classes_fr.json").read_text(encoding="utf-8"))

    session = ort.InferenceSession(
        str(MODEL_DIR / "tomate_mobilenetv3.onnx"),
        providers=["CPUExecutionProvider"],
    )

    yield

    session = None


app = FastAPI(
    title="Jaden Konekté - Service CNN",
    lifespan=lifespan,
)


def preparer_image(contenu: bytes) -> np.ndarray:
    try:
        with Image.open(io.BytesIO(contenu)) as source:
            if source.format not in {"JPEG", "PNG"} or source.width * source.height > Image.MAX_IMAGE_PIXELS:
                raise ValueError("Image invalide ou trop grande")
            image = ImageOps.exif_transpose(source)
            image = image.convert("RGB")
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
    ):
        raise ValueError("Image invalide ou non prise en charge")

    largeur, hauteur = image.size
    if largeur < 32 or hauteur < 32:
        raise ValueError("Résolution insuffisante")

    # Équivalent à Resize(256) de torchvision.
    ratio = 256 / min(largeur, hauteur)
    taille = (round(largeur * ratio), round(hauteur * ratio))

    if max(taille) > 8192:
        raise ValueError("Proportions de l’image non prises en charge")
    image = image.resize(taille, Image.Resampling.BILINEAR)

    # CenterCrop(224)
    gauche = (image.width - 224) // 2
    haut = (image.height - 224) // 2

    image = image.crop(
        (gauche, haut, gauche + 224, haut + 224)
    )

    tableau = np.asarray(image, dtype=np.float32) / 255.0
    tableau = (tableau - MEAN) / STD
    tableau = tableau.transpose(2, 0, 1)

    return np.expand_dims(tableau, axis=0)


def predire(contenu: bytes) -> dict:
    entree = preparer_image(contenu)

    logits = session.run(
        ["logits"],
        {"image": entree},
    )[0][0]

    # Softmax stable numériquement.
    logits = logits - np.max(logits)
    exp = np.exp(logits)
    probabilites = exp / np.sum(exp)

    indice = int(np.argmax(probabilites))

    return {
        "classe": libelles[classes[indice]],
        "confiance": float(probabilites[indice]),
        "version_modele": MODEL_VERSION,
    }


@app.get("/health")
def health():
    return {"statut": "ok"}


@app.post("/predictions")
async def prediction(image: UploadFile = File(...)):
    if image.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(
            status_code=415,
            detail="Seules les images JPEG et PNG sont acceptées",
        )

    contenu = await image.read(MAX_BYTES + 1)

    if len(contenu) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Image trop volumineuse (maximum 5 Mo)",
        )

    if not contenu:
        raise HTTPException(
            status_code=400,
            detail="Image vide",
        )

    try:
        return await run_in_threadpool(predire, contenu)
    except ValueError as erreur:
        raise HTTPException(
            status_code=422,
            detail=str(erreur),
        )
