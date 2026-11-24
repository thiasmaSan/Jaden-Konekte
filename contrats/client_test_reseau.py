"""
Outil en ligne de commande pour tester le réseau régional d'alertes.

    pip install httpx
    python client_test_reseau.py --central http://SERVEUR-CENTRAL:8080 inscrire \
        --groupe groupe-3 --nom "Jaden Lanmou" \
        --url-base http://10.2.2.31:8000 --webhook http://10.2.2.31:8000/webhooks/alertes \
        --secret "un-secret-long-et-aleatoire"
    python client_test_reseau.py --central ... publier --token <TOKEN> --commune Baillif
    python client_test_reseau.py --central ... lister
    python client_test_reseau.py --central ... livraisons alt_1234abcd
"""
import argparse
import json
import uuid
from datetime import datetime, timezone

import httpx


def afficher(r: httpx.Response) -> None:
    print(r.status_code, r.headers.get("content-type", ""))
    try:
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    except ValueError:
        print(r.text)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--central", default="http://localhost:8080")
    sub = ap.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("inscrire")
    i.add_argument("--groupe", required=True)
    i.add_argument("--nom", required=True)
    i.add_argument("--url-base", required=True)
    i.add_argument("--webhook", required=True)
    i.add_argument("--secret", required=True)
    i.add_argument("--membres", nargs="*", default=[])

    p = sub.add_parser("publier")
    p.add_argument("--token", required=True)
    p.add_argument("--culture", default="tomate")
    p.add_argument("--maladie", default="tomato_late_blight")
    p.add_argument("--score", type=float, default=0.91)
    p.add_argument("--gravite", default="moyenne", choices=["faible", "moyenne", "forte"])
    p.add_argument("--commune", default="Baillif")

    sub.add_parser("lister")
    sub.add_parser("plateformes")
    lv = sub.add_parser("livraisons")
    lv.add_argument("alerte_id")

    a = ap.parse_args()
    with httpx.Client(base_url=a.central, timeout=10) as c:
        if a.cmd == "inscrire":
            afficher(c.post("/v1/plateformes", json={
                "groupe": a.groupe, "nom": a.nom, "membres": a.membres,
                "url_base": a.url_base, "url_webhook": a.webhook, "secret": a.secret}))
        elif a.cmd == "publier":
            afficher(c.post(
                "/v1/alertes",
                headers={"Authorization": f"Bearer {a.token}", "Idempotency-Key": str(uuid.uuid4())},
                json={"type": "maladie", "culture": a.culture, "maladie": a.maladie,
                      "score": a.score, "gravite": a.gravite, "commune": a.commune,
                      "observee_le": datetime.now(timezone.utc).isoformat()}))
        elif a.cmd == "lister":
            afficher(c.get("/v1/alertes"))
        elif a.cmd == "plateformes":
            afficher(c.get("/v1/plateformes"))
        elif a.cmd == "livraisons":
            afficher(c.get(f"/v1/alertes/{a.alerte_id}/livraisons"))


if __name__ == "__main__":
    main()
