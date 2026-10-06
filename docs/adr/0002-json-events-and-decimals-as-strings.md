# ADR 0002: JSON events without schema, decimals as strings

Status: accepted

## Context

Debezium change events are read by Spark in the bronze layer. The default
settings embed a schema in each message and encode NUMERIC columns as binary.

## Decision

- Use the JSON converter with `schemas.enable=false`.
- Use `decimal.handling.mode=string` so that amounts keep full precision and
  stay readable.
- Keep the full event envelope (before, after, op, source, ts_ms). Do not
  flatten it.

## Alternatives considered

- Avro with a schema registry: stricter and more compact, but one more service
  to run. A possible improvement later.
- Decimals as double: simple, but can lose precision for money.
- Flattened events (unwrap SMT): simpler to read, but loses the before image,
  the operation type and the log position needed for ordering and deletes.

## Consequences

- Schema changes in the source are not blocked by a registry, so the bronze
  layer must handle new or missing fields.
- Amounts must be cast from string to decimal in the silver layer.
