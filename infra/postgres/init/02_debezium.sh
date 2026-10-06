#!/bin/bash
# Creates the CDC user and the publication. Safe to run several times.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'debezium') THEN
    CREATE ROLE debezium WITH LOGIN REPLICATION PASSWORD '${DEBEZIUM_PASSWORD}';
  END IF;
END
\$\$;
GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO debezium;
GRANT USAGE ON SCHEMA public TO debezium;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO debezium;
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_publication WHERE pubname = 'dbz_publication') THEN
    CREATE PUBLICATION dbz_publication FOR TABLE carriers, warehouses, products, customers, orders, order_items, shipments, stock_levels, stock_movements;
  END IF;
END
\$\$;
EOSQL
