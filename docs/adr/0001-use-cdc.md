# ADR 0001: Capture changes with CDC instead of batch extraction

Status: accepted

## Context

The platform needs to follow orders, shipments and stock almost in real time.
The source is a PostgreSQL database used by an application.

## Decision

Use Change Data Capture with Debezium. Debezium reads the PostgreSQL write-ahead
log and publishes every insert, update and delete to Kafka.

## Alternatives considered

- Query the tables every few minutes using an `updated_at` column. Simple, but it
  misses deletes and intermediate states, and it adds load on the source.
- Daily full extracts. Simple, but the data is up to one day old.
- Triggers writing to audit tables. It changes the source schema and slows down writes.

## Consequences

- Deletes and every intermediate state are captured.
- The source needs logical replication enabled (`wal_level = logical`).
- Delivery is at least once: the same event can arrive twice. All downstream
  steps must be idempotent.
- More components to run and monitor (Kafka, Kafka Connect).
