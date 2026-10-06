# Source data contract

Source: PostgreSQL database of the order management application (simulated).
All tables are in the `public` schema. Every table has `REPLICA IDENTITY FULL`.

| Table | Key | Role |
|---|---|---|
| customers | customer_id | Customers (retail or wholesale) |
| products | product_id | Product catalog and current price |
| warehouses | warehouse_id | Three warehouses |
| carriers | carrier_id | Delivery companies |
| orders | order_id | Orders and their status |
| order_items | order_item_id | Lines of an order (cascade delete with the order) |
| shipments | shipment_id | One shipment per shipped order |
| stock_levels | (warehouse_id, product_id) | Current stock |
| stock_movements | movement_id | Stock log. Quantity is signed |

## Order life cycle

created -> confirmed -> picked -> shipped -> delivered. About 3 percent of orders
are cancelled right after creation, and their stock is given back.
Cancelled orders older than 2 days are deleted.

## Time

All timestamps are business time (`timestamptz`, UTC). During a backfill, they
are in the past. The commit time of a change is the time when the row was
really written, and it is available from the change events in the next step.

## Data quality issues injected on purpose

- Customers: about 2 percent malformed emails, 2 percent missing emails,
  3 percent missing phones, city with inconsistent case or a trailing space,
  1 percent missing city.
- Shipments: about 1 percent have `delivered_at` before `shipped_at`.
- Order lines can be smaller than requested when the stock is too low.
