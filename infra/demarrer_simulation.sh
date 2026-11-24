#!/bin/sh
# À lancer explicitement : prépare uniquement p1/p2/p3 dans l'exploitation choisie.
set -eu
cd "$(dirname "$0")"
usage() {
    echo "Usage : sh infra/demarrer_simulation.sh ID ou --code CODE_EXPLOITATION" >&2
    exit 1
}
case "${1:-}" in
    --code)
        [ "$#" -eq 2 ] || usage
        code=$2
        case "$code" in
            ''|*[!A-Za-z0-9_-]*) usage ;;
        esac
        [ "${#code}" -le 30 ] || usage
        docker compose up -d --wait db
        exploitation_id=$(docker compose exec -T db psql -U jaden -d jaden -At \
            -c "SELECT id FROM exploitation WHERE code = '$code';")
        if [ -z "$exploitation_id" ]; then
            echo "Exploitation introuvable : $code. Inscris-toi d’abord dans le tableau de bord." >&2
            exit 1
        fi
        ;;
    *)
        [ "$#" -le 1 ] || usage
        exploitation_id=${1:-1}
        case "$exploitation_id" in
            ''|*[!0-9]*) usage ;;
        esac
        docker compose up -d --wait db
        ;;
esac
docker compose run --rm --no-deps --build ingestion \
    python -m app.preparer_simulation --exploitation-id "$exploitation_id"
code=$(docker compose exec -T db psql -U jaden -d jaden -At \
    -c "SELECT code FROM exploitation WHERE id = $exploitation_id;")
case "$code" in
    ''|*[!A-Za-z0-9_-]*) echo "Code d'exploitation MQTT invalide" >&2; exit 1 ;;
esac
export SIMULATION_EXPLOITATION_CODE="$code"
# Recharge les ACL pour le code réel, sans renouveler les mots de passe ni les volumes.
docker compose up -d --force-recreate mqtt-init
docker compose up -d --force-recreate --no-deps mqtt
docker compose up -d --build ingestion
docker compose --profile simu up -d --build --force-recreate --no-deps simulateur
echo "Simulation démarrée pour l'exploitation $exploitation_id ($code)."
echo "Actualiser le tableau de bord sur http://127.0.0.1:8000/dashboard."
