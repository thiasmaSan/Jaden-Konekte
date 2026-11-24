"""Interroge les questions de référence et écrit les réponses à relire."""
import argparse
import getpass
import json
import os
from pathlib import Path

import httpx


def poser_question(client, question):
    fragments = []
    sources = []
    evenement = None
    with client.stream("POST", "/api/v1/assistant/questions", json={"question": question}) as flux:
        flux.raise_for_status()
        for ligne in flux.iter_lines():
            if ligne.startswith("event:"):
                evenement = ligne[6:].strip()
            if not ligne.startswith("data:"):
                continue
            donnees = json.loads(ligne[5:])
            if evenement == "fragment":
                fragments.append(donnees["texte"])
            elif evenement == "sources":
                sources = donnees["sources"]
            elif evenement == "erreur":
                raise RuntimeError(donnees["message"])
            elif evenement == "fin":
                return "".join(fragments), sources
    raise RuntimeError("Flux SSE incomplet")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--sortie", type=Path, default=Path("evaluation-rag.jsonl"))
    args = parser.parse_args()

    jeton = os.getenv("JADEN_JETON") or getpass.getpass("Jeton JWT : ")
    questions = json.loads(Path(__file__).with_name("questions_reference.json").read_text(encoding="utf-8"))
    selection = questions[:10] + [questions[-1]]
    reussites = erreurs = 0
    with httpx.Client(base_url=args.url, timeout=180, headers={"Authorization": f"Bearer {jeton}"}) as client:
        with args.sortie.open("x", encoding="utf-8") as sortie:
            for cible in selection:
                try:
                    reponse, sources = poser_question(client, cible["question"])
                    attendue = cible["source_attendue"]
                    citees = {source["source"] for source in sources}
                    source_ok = (
                        attendue in citees if attendue
                        else not citees and "je ne trouve pas la réponse" in reponse.lower()
                    )
                    reussites += source_ok
                    resultat = dict(cible, reponse=reponse, sources=sources, source_ok=source_ok)
                except (httpx.HTTPError, ValueError, RuntimeError) as erreur:
                    erreurs += 1
                    resultat = dict(cible, erreur=str(erreur))
                sortie.write(json.dumps(resultat, ensure_ascii=False) + "\n")
                sortie.flush()
                print(f"Question {cible['id']} terminée.", flush=True)
    print(f"Sources attendues ou abstention sans source : {reussites}/{len(selection)}")
    print(f"Requêtes en erreur : {erreurs}. Comparer les réponses aux éléments attendus.")
    return int(erreurs > 0)


if __name__ == "__main__":
    raise SystemExit(main())
