#!/usr/bin/env bash
# Registers (or updates) the Debezium connector. Safe to run several times.
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; source .env; set +a

echo "Waiting for Kafka Connect..."
ready=0
for _ in $(seq 1 60); do
  if curl -sf http://localhost:8083/connectors > /dev/null; then ready=1; break; fi
  sleep 2
done
if [ "$ready" -ne 1 ]; then
  echo "Kafka Connect did not start in time. Check: docker compose logs connect" >&2
  exit 1
fi

sed -e "s/__DB_PASSWORD__/${DEBEZIUM_PASSWORD}/" -e "s/__DB_NAME__/${POSTGRES_DB}/" \
  infra/debezium/orders-connector.json \
  | curl -sS -X PUT -H "Content-Type: application/json" --data @- \
    http://localhost:8083/connectors/orders-app-connector/config
echo
echo "Connector registered."
