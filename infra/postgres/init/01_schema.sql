CREATE TABLE carriers (
    carrier_id SERIAL PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    is_active  BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE warehouses (
    warehouse_id SERIAL PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    city         TEXT NOT NULL
);

CREATE TABLE products (
    product_id SERIAL PRIMARY KEY,
    sku        TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL,
    category   TEXT NOT NULL,
    unit_price NUMERIC(10,2) NOT NULL CHECK (unit_price > 0),
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE customers (
    customer_id SERIAL PRIMARY KEY,
    full_name   TEXT NOT NULL,
    email       TEXT,
    phone       TEXT,
    city        TEXT,
    segment     TEXT NOT NULL CHECK (segment IN ('retail', 'wholesale')),
    created_at  TIMESTAMPTZ NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL
);

CREATE TABLE orders (
    order_id     BIGSERIAL PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers (customer_id),
    warehouse_id INTEGER NOT NULL REFERENCES warehouses (warehouse_id),
    status       TEXT NOT NULL CHECK (status IN ('created', 'confirmed', 'picked', 'shipped', 'delivered', 'cancelled')),
    total_amount NUMERIC(12,2) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL,
    promised_at  TIMESTAMPTZ NOT NULL
);

CREATE TABLE order_items (
    order_item_id BIGSERIAL PRIMARY KEY,
    order_id      BIGINT NOT NULL REFERENCES orders (order_id) ON DELETE CASCADE,
    product_id    INTEGER NOT NULL REFERENCES products (product_id),
    quantity      INTEGER NOT NULL CHECK (quantity > 0),
    unit_price    NUMERIC(10,2) NOT NULL
);

CREATE TABLE shipments (
    shipment_id  BIGSERIAL PRIMARY KEY,
    order_id     BIGINT NOT NULL UNIQUE REFERENCES orders (order_id),
    carrier_id   INTEGER NOT NULL REFERENCES carriers (carrier_id),
    status       TEXT NOT NULL CHECK (status IN ('in_transit', 'delivered')),
    shipped_at   TIMESTAMPTZ NOT NULL,
    delivered_at TIMESTAMPTZ
);

CREATE TABLE stock_levels (
    warehouse_id     INTEGER NOT NULL REFERENCES warehouses (warehouse_id),
    product_id       INTEGER NOT NULL REFERENCES products (product_id),
    quantity_on_hand INTEGER NOT NULL CHECK (quantity_on_hand >= 0),
    updated_at       TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (warehouse_id, product_id)
);

-- Quantity is signed: negative for outbound, positive for inbound.
-- reference_order_id has no foreign key on purpose (audit log).
CREATE TABLE stock_movements (
    movement_id        BIGSERIAL PRIMARY KEY,
    warehouse_id       INTEGER NOT NULL REFERENCES warehouses (warehouse_id),
    product_id         INTEGER NOT NULL REFERENCES products (product_id),
    movement_type      TEXT NOT NULL CHECK (movement_type IN ('inbound', 'outbound', 'adjustment')),
    quantity           INTEGER NOT NULL,
    reference_order_id BIGINT,
    created_at         TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_order_items_order ON order_items (order_id);
CREATE INDEX idx_orders_status_updated ON orders (status, updated_at);

-- Keep the "before" image of every change available for CDC.
ALTER TABLE carriers        REPLICA IDENTITY FULL;
ALTER TABLE warehouses      REPLICA IDENTITY FULL;
ALTER TABLE products        REPLICA IDENTITY FULL;
ALTER TABLE customers       REPLICA IDENTITY FULL;
ALTER TABLE orders          REPLICA IDENTITY FULL;
ALTER TABLE order_items     REPLICA IDENTITY FULL;
ALTER TABLE shipments       REPLICA IDENTITY FULL;
ALTER TABLE stock_levels    REPLICA IDENTITY FULL;
ALTER TABLE stock_movements REPLICA IDENTITY FULL;
