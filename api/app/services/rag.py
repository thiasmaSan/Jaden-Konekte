import hashlib
import json
import os
import re
from math import isfinite
from pathlib import Path

import httpx
from psycopg.rows import dict_row

from ..database import get_connection

FICHES = Path(os.getenv("RAG_FICHES", Path(__file__).resolve().parents[3] / "ia/rag/fiches"))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
MODELE_EMBEDDING = os.getenv("RAG_MODELE_EMBEDDING", "embeddinggemma")
MODELE_LLM = os.getenv("RAG_MODELE_LLM", "qwen2.5:1.5b")
DISTANCE_MAX = 0.65
HORS_CORPUS = "Je ne trouve pas la réponse dans les fiches techniques."


def decouper_fiches():
    passages = []
    for fiche in sorted(FICHES.glob("*.md")):
        texte = fiche.read_text(encoding="utf-8")
        blocs = re.split(r"^## (.+)$", texte, flags=re.MULTILINE)
        for section, contenu in zip(blocs[1::2], blocs[2::2]):
            if contenu.strip():
                passages.append((fiche.name, section.strip(), contenu.strip()))
    if not passages:
        raise ValueError("Corpus agronomique vide")
    return passages


async def embeddings(client, textes):
    reponse = await client.post("/api/embed", json={
        "model": MODELE_EMBEDDING, "input": textes, "dimensions": 384,
    })
    reponse.raise_for_status()
    vecteurs = reponse.json()["embeddings"]
    if len(vecteurs) != len(textes) or any(
        len(vecteur) != 384 or not all(map(isfinite, vecteur)) or not any(vecteur)
        for vecteur in vecteurs
    ):
        raise ValueError("Dimensions ou valeurs d’embedding invalides")
    return [json.dumps(vecteur) for vecteur in vecteurs]


def rechercher(empreinte, vecteur):
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT source, section, contenu, embedding <=> %s::vector AS distance
               FROM passage WHERE index_corpus = %s
               ORDER BY distance, id LIMIT 4""",
            (vecteur, empreinte),
        )
        return cur.fetchall()


def enregistrer_index(empreinte, passages, vecteurs):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(540282)")
        cur.execute("SELECT 1 FROM passage WHERE index_corpus = %s LIMIT 1", (empreinte,))
        if cur.fetchone():
            return
        cur.executemany(
            """INSERT INTO passage (source, section, contenu, index_corpus, embedding)
               VALUES (%s, %s, %s, %s, %s::vector)""",
            [(*passage, empreinte, vecteur) for passage, vecteur in zip(passages, vecteurs)],
        )


def empreinte_corpus(passages):
    return hashlib.sha256(json.dumps(
        [MODELE_EMBEDDING, 384, passages], ensure_ascii=False
    ).encode()).hexdigest()
