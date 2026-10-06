# Architecture

```mermaid
flowchart LR
    A[(PostgreSQL orders app)] -->|WAL| B[Debezium]
    B --> C[Kafka]
    C --> D[Spark Streaming]
    D --> E[(Bronze: Delta on MinIO)]
    E --> F[Silver: MERGE and SCD2]
    F --> G[Gold: star schema and KPIs]
    G --> H[(Postgres warehouse)]
    H --> I[Metabase]
    P[Prefect] -. orchestrates .-> F
    P -. orchestrates .-> G
    Q[Quality checks] -. gate .-> G
    M[Grafana] -. monitors .-> C
```

## Layers

| Layer | Content |
|---|---|
| Bronze | Raw change events (operation, before, after, timestamp), append only |
| Silver | Current state of each table, cleaned, with history for customers and products |
| Gold | Star schema and KPI tables, published to a warehouse for BI |

The status of each component is tracked in the README. This diagram describes
the target architecture, not what is built today.
