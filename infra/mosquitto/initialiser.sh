#!/bin/sh
set -eu
umask 077

code=${SIMULATION_EXPLOITATION_CODE:-}
if [ -z "$code" ]; then
    if [ -s /auth/simulation-code ]; then
        code=$(cat /auth/simulation-code)
    else
        code=expl-1
    fi
fi
case "$code" in
  ''|*[!A-Za-z0-9_-]*) echo "Code d'exploitation MQTT invalide" >&2; exit 1 ;;
esac
if [ "${#code}" -gt 30 ]; then
    echo "Code d'exploitation trop long" >&2
    exit 1
fi
printf '%s' "$code" > /auth/simulation-code
printf '%s' "$code" > /credentials/simulateur/exploitation
chmod 644 /auth/simulation-code
chmod 444 /credentials/simulateur/exploitation

# Les mots de passe restent dans des volumes Docker dédiés, jamais dans le dépôt.
for compte in ingestion simulateur api; do
    fichier="/credentials/$compte/password"
    if [ ! -s "$fichier" ]; then
        od -An -N32 -tx1 /dev/urandom | tr -d ' \n' > "$fichier"
    fi
    chmod 444 "$fichier"
done

mosquitto_passwd -b -c /auth/passwd.tmp ingestion "$(cat /credentials/ingestion/password)"
mosquitto_passwd -b /auth/passwd.tmp simulateur "$(cat /credentials/simulateur/password)"
mosquitto_passwd -b /auth/passwd.tmp api "$(cat /credentials/api/password)"
chmod 644 /auth/passwd.tmp
mv /auth/passwd.tmp /auth/passwd

{
    echo 'user ingestion'
    echo 'topic read $SYS/broker/version'
    for grandeur in sol/humidite air/temperature air/luminosite pluvio/intensite; do
        echo "topic read jaden/+/+/$grandeur"
    done
    echo 'user api'
    echo 'topic write jaden/+/+/vanne/cmd'
    echo 'topic read jaden/+/+/vanne/etat'
    echo 'topic read jaden/+/+/statut'
    echo 'user simulateur'
    for grandeur in sol/humidite air/temperature air/luminosite pluvio/intensite vanne/etat statut; do
        echo "topic write jaden/$code/+/$grandeur"
    done
    echo "topic read jaden/$code/+/vanne/cmd"
} > /auth/acl.tmp
chmod 644 /auth/acl.tmp
mv /auth/acl.tmp /auth/acl
echo "Comptes MQTT prêts ; simulateur limité à l'exploitation $code"
