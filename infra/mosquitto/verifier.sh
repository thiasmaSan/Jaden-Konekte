#!/bin/sh
set -eu
exec mosquitto_sub -h localhost -u ingestion \
    -P "$(cat /run/credentials/ingestion/password)" \
    -t '$SYS/broker/version' -C 1 -W 5 >/dev/null 2>&1
