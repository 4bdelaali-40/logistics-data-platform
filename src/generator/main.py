"""Order management data generator.

Simulates the operational database of a distributor: customers, products,
orders, shipments and stock. A simulated clock can start in the past and run
faster than real time until it reaches the real time (backfill), then it
continues in real time.
"""
import argparse
import heapq
import os
import random
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import psycopg
from tqdm import tqdm

# city -> (weight, city of the warehouse that serves it)
CITIES = {
    "Casablanca": (30, "Casablanca"), "Rabat": (12, "Casablanca"),
    "Marrakech": (12, "Marrakech"), "Fes": (8, "Casablanca"),
    "Tanger": (10, "Tanger"), "Agadir": (7, "Marrakech"),
    "Meknes": (5, "Casablanca"), "Oujda": (4, "Casablanca"),
    "Kenitra": (5, "Casablanca"), "Tetouan": (4, "Tanger"),
}
WAREHOUSES = [("WH Casablanca", "Casablanca"), ("WH Tanger", "Tanger"), ("WH Marrakech", "Marrakech")]
# carrier name -> probability of a late delivery
CARRIERS = [("Atlas Express", 0.05), ("Sahara Cargo", 0.12), ("Rif Logistics", 0.20), ("Medina Courier", 0.08)]
FIRST_NAMES = ["Youssef", "Fatima", "Mohamed", "Khadija", "Amine", "Salma", "Omar", "Imane", "Hamza", "Nadia", "Karim", "Samira"]
LAST_NAMES = ["Benali", "El Idrissi", "Alaoui", "Bennani", "Tazi", "Lahlou", "Berrada", "Chraibi", "Fassi", "Amrani", "Zniber", "Mansouri"]
CATALOG = {
    "Beverages": ["Mineral water", "Orange juice", "Mint tea", "Cola", "Coffee beans"],
    "Grocery": ["Olive oil", "Couscous", "Rice", "Sugar", "Flour", "Tomato sauce"],
    "Dairy": ["Milk", "Yogurt", "Butter", "Cheese"],
    "Household": ["Dish soap", "Laundry detergent", "Paper towels", "Bleach"],
    "Snacks": ["Biscuits", "Chocolate bar", "Almonds", "Dates"],
}
SIZES = ["250g", "500g", "1kg", "1L", "2L", "6-pack", "12-pack"]
NEXT_STATUS = {"created": "confirmed", "confirmed": "picked", "picked": "shipped", "shipped": "delivered"}


class SimClock:
    """Starts at sim_start and runs `speedup` times faster than real time,
    but never goes beyond the real time."""

    def __init__(self, sim_start, speedup):
        self.sim_start = sim_start
        self.speedup = speedup
        self.real_start = datetime.now(timezone.utc)

    def _sim(self, real):
        return self.sim_start + (real - self.real_start) * self.speedup

    def now(self):
        real = datetime.now(timezone.utc)
        return min(self._sim(real), real)

    def caught_up(self):
        real = datetime.now(timezone.utc)
        return self._sim(real) >= real


class World:
    """In-memory caches and the schedule of open orders."""

    def __init__(self):
        self.customers = {}      # customer_id -> (city, segment)
        self.customer_ids = []
        self.prices = {}         # product_id -> Decimal
        self.wh_by_city = {}
        self.carriers = []
        self.heap = []           # (due, order_id, status)
        self.stats = Counter()
        self.last_hour = None


def connect():
    return psycopg.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        dbname=os.environ.get("DB_NAME", "orders_app"),
        user=os.environ.get("DB_USER", "app"),
        password=os.environ["DB_PASSWORD"],
    )


def traffic_factor(ts):
    """More orders during the day. Hours are shifted by +1 (Morocco)."""
    hour = (ts.hour + 1) % 24
    if hour < 7 or hour >= 21:
        return 0.3
    return 1.3 if 9 <= hour < 18 else 0.8


def make_customer(ts):
    """Return one customer row. A few rows contain bad data on purpose."""
    first, last = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
    city = random.choices(list(CITIES), weights=[v[0] for v in CITIES.values()])[0]
    email = f"{first}.{last}{random.randint(1, 9999)}@example.com".lower().replace(" ", "")
    phone = f"+2126{random.randint(10000000, 99999999)}"
    r = random.random()
    if r < 0.02:
        email = email.replace("@", "")      # malformed email
    elif r < 0.04:
        email = None                        # missing email
    if random.random() < 0.03:
        phone = None
    r = random.random()
    if r < 0.03:
        city = city.upper()                 # inconsistent casing
    elif r < 0.06:
        city = city + " "                   # trailing space
    elif r < 0.07:
        city = None                         # missing city
    segment = "wholesale" if random.random() < 0.2 else "retail"
    return (f"{first} {last}", email, phone, city, segment, ts, ts)


def make_plan(order_id, carriers):
    """Lifecycle of an order. It only depends on the order id, so it can be
    rebuilt after a restart."""
    rng = random.Random(order_id)
    carrier = carriers[rng.randrange(len(carriers))]
    late = rng.random() < carrier["late_prob"]
    transit = rng.uniform(12, 60) + (rng.uniform(24, 72) if late else 0)
    return {
        "cancel": rng.random() < 0.03,
        "carrier_id": carrier["carrier_id"],
        "created": timedelta(minutes=rng.uniform(5, 60)),
        "confirmed": timedelta(hours=rng.uniform(1, 6)),
        "picked": timedelta(hours=rng.uniform(1, 8)),
        "shipped": timedelta(hours=transit),
    }


def load_world(conn):
    world = World()
    with conn.cursor() as cur:
        cur.execute("SELECT customer_id, city, segment FROM customers")
        world.customers = {cid: (city, seg) for cid, city, seg in cur.fetchall()}
        world.customer_ids = list(world.customers)
        cur.execute("SELECT product_id, unit_price FROM products WHERE is_active")
        world.prices = dict(cur.fetchall())
        cur.execute("SELECT city, warehouse_id FROM warehouses")
        world.wh_by_city = dict(cur.fetchall())
        late = dict(CARRIERS)
        cur.execute("SELECT carrier_id, name FROM carriers ORDER BY carrier_id")
        world.carriers = [{"carrier_id": cid, "late_prob": late.get(name, 0.1)} for cid, name in cur.fetchall()]
        cur.execute("SELECT order_id, status, updated_at FROM orders WHERE status NOT IN ('delivered', 'cancelled')")
        for order_id, status, updated_at in cur.fetchall():
            plan = make_plan(order_id, world.carriers)
            heapq.heappush(world.heap, (updated_at + plan[status], order_id, status))
    conn.commit()
    return world


def seed(conn, n_customers, n_products):
    now = datetime.now(timezone.utc)
    base = now - timedelta(days=400)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM carriers")
        if cur.fetchone()[0] > 0:
            print("The database is already seeded. Nothing to do.")
            return
        cur.executemany("INSERT INTO carriers (name) VALUES (%s)", [(n,) for n, _ in CARRIERS])
        cur.executemany("INSERT INTO warehouses (name, city) VALUES (%s, %s)", WAREHOUSES)
        combos = [(c, i, s) for c, items in CATALOG.items() for i in items for s in SIZES]
        chosen = random.sample(combos, min(n_products, len(combos)))
        cur.executemany(
            "INSERT INTO products (sku, name, category, unit_price, updated_at) VALUES (%s, %s, %s, %s, %s)",
            [(f"SKU-{k:04d}", f"{item} {size}", cat, round(random.uniform(5, 120), 2), base)
             for k, (cat, item, size) in enumerate(chosen, 1)],
        )
        customers = [make_customer(base + timedelta(days=random.uniform(0, 390)))
                     for _ in tqdm(range(n_customers), desc="Creating customers")]
        cur.executemany(
            "INSERT INTO customers (full_name, email, phone, city, segment, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)", customers)
        cur.execute(
            "INSERT INTO stock_levels (warehouse_id, product_id, quantity_on_hand, updated_at) "
            "SELECT w.warehouse_id, p.product_id, 50 + floor(random() * 450)::int, %s "
            "FROM warehouses w CROSS JOIN products p", (base,))
    conn.commit()
    print(f"Seed done: {len(chosen)} products, {n_customers} customers, "
          f"{len(WAREHOUSES)} warehouses, {len(CARRIERS)} carriers.")


def create_order(conn, world, ts):
    with conn.cursor() as cur:
        new_customer = None
        if random.random() < 0.05:
            row = make_customer(ts)
            cur.execute(
                "INSERT INTO customers (full_name, email, phone, city, segment, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING customer_id", row)
            customer_id = cur.fetchone()[0]
            new_customer = (customer_id, row[3], row[4])
            city, segment = row[3], row[4]
        else:
            customer_id = random.choice(world.customer_ids)
            city, segment = world.customers[customer_id]
        wh_city = CITIES.get((city or "Casablanca").strip().title(), (0, "Casablanca"))[1]
        warehouse_id = world.wh_by_city[wh_city]

        lines = []
        for product_id in random.sample(list(world.prices), random.randint(1, 5)):
            wanted = random.randint(5, 40) if segment == "wholesale" else random.randint(1, 5)
            cur.execute(
                "SELECT quantity_on_hand FROM stock_levels WHERE warehouse_id = %s AND product_id = %s FOR UPDATE",
                (warehouse_id, product_id))
            fulfilled = min(wanted, cur.fetchone()[0])
            if fulfilled > 0:
                cur.execute(
                    "UPDATE stock_levels SET quantity_on_hand = quantity_on_hand - %s, updated_at = %s "
                    "WHERE warehouse_id = %s AND product_id = %s", (fulfilled, ts, warehouse_id, product_id))
                lines.append((product_id, fulfilled, world.prices[product_id]))
        if not lines:
            conn.rollback()
            world.stats["lost_sales"] += 1
            return

        total = sum(qty * price for _, qty, price in lines)
        promised_at = ts + timedelta(hours=random.uniform(48, 96))
        cur.execute(
            "INSERT INTO orders (customer_id, warehouse_id, status, total_amount, created_at, updated_at, promised_at) "
            "VALUES (%s, %s, 'created', %s, %s, %s, %s) RETURNING order_id",
            (customer_id, warehouse_id, total, ts, ts, promised_at))
        order_id = cur.fetchone()[0]
        cur.executemany(
            "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (%s, %s, %s, %s)",
            [(order_id, pid, qty, price) for pid, qty, price in lines])
        cur.executemany(
            "INSERT INTO stock_movements (warehouse_id, product_id, movement_type, quantity, reference_order_id, created_at) "
            "VALUES (%s, %s, 'outbound', %s, %s, %s)",
            [(warehouse_id, pid, -qty, order_id, ts) for pid, qty, _ in lines])
    conn.commit()

    if new_customer:  # update caches only after a successful commit
        world.customers[new_customer[0]] = (new_customer[1], new_customer[2])
        world.customer_ids.append(new_customer[0])
    world.stats["orders"] += 1
    plan = make_plan(order_id, world.carriers)
    heapq.heappush(world.heap, (ts + plan["created"], order_id, "created"))


def process_step(conn, world, due, order_id, status):
    """Move one order to its next status. `due` is the event time."""
    plan = make_plan(order_id, world.carriers)
    new_status = None
    with conn.cursor() as cur:
        if status == "created" and plan["cancel"]:
            cur.execute(
                "UPDATE orders SET status = 'cancelled', updated_at = %s WHERE order_id = %s RETURNING warehouse_id",
                (due, order_id))
            warehouse_id = cur.fetchone()[0]
            cur.execute("SELECT product_id, quantity FROM order_items WHERE order_id = %s", (order_id,))
            for product_id, qty in cur.fetchall():  # give the stock back
                cur.execute(
                    "UPDATE stock_levels SET quantity_on_hand = quantity_on_hand + %s, updated_at = %s "
                    "WHERE warehouse_id = %s AND product_id = %s", (qty, due, warehouse_id, product_id))
                cur.execute(
                    "INSERT INTO stock_movements (warehouse_id, product_id, movement_type, quantity, reference_order_id, created_at) "
                    "VALUES (%s, %s, 'adjustment', %s, %s, %s)", (warehouse_id, product_id, qty, order_id, due))
        else:
            new_status = NEXT_STATUS[status]
            cur.execute("UPDATE orders SET status = %s, updated_at = %s WHERE order_id = %s",
                        (new_status, due, order_id))
            if new_status == "shipped":
                cur.execute(
                    "INSERT INTO shipments (order_id, carrier_id, status, shipped_at) VALUES (%s, %s, 'in_transit', %s)",
                    (order_id, plan["carrier_id"], due))
            elif new_status == "delivered":
                if random.random() < 0.01:  # bad data on purpose: delivered before shipped
                    cur.execute(
                        "UPDATE shipments SET status = 'delivered', delivered_at = shipped_at - interval '2 hours' "
                        "WHERE order_id = %s", (order_id,))
                else:
                    cur.execute("UPDATE shipments SET status = 'delivered', delivered_at = %s WHERE order_id = %s",
                                (due, order_id))
    conn.commit()
    world.stats["steps"] += 1
    if new_status in ("confirmed", "picked", "shipped"):
        heapq.heappush(world.heap, (due + plan[new_status], order_id, new_status))


def hourly_maintenance(conn, world, now):
    """Restock, customer changes, price changes and purge of old cancelled orders."""
    price_updates, customer_updates = {}, {}
    with conn.cursor() as cur:
        cur.execute("SELECT warehouse_id, product_id FROM stock_levels WHERE quantity_on_hand < 30 LIMIT 60")
        for warehouse_id, product_id in cur.fetchall():
            if random.random() > 0.15:  # supplier lead time: most low-stock pairs wait
                continue
            qty = random.randint(150, 400)
            cur.execute(
                "UPDATE stock_levels SET quantity_on_hand = quantity_on_hand + %s, updated_at = %s "
                "WHERE warehouse_id = %s AND product_id = %s", (qty, now, warehouse_id, product_id))
            cur.execute(
                "INSERT INTO stock_movements (warehouse_id, product_id, movement_type, quantity, created_at) "
                "VALUES (%s, %s, 'inbound', %s, %s)", (warehouse_id, product_id, qty, now))

        for customer_id in random.sample(world.customer_ids, min(len(world.customer_ids), max(1, len(world.customer_ids) // 400))):
            city = random.choices(list(CITIES), weights=[v[0] for v in CITIES.values()])[0]
            cur.execute("UPDATE customers SET city = %s, updated_at = %s WHERE customer_id = %s",
                        (city, now, customer_id))
            customer_updates[customer_id] = (city, world.customers[customer_id][1])

        for product_id in random.sample(list(world.prices), max(1, len(world.prices) // 200)):
            price = (world.prices[product_id] * Decimal(str(round(random.uniform(0.9, 1.1), 3)))).quantize(Decimal("0.01"))
            cur.execute("UPDATE products SET unit_price = %s, updated_at = %s WHERE product_id = %s",
                        (price, now, product_id))
            price_updates[product_id] = price

        cur.execute("DELETE FROM orders WHERE status = 'cancelled' AND updated_at < %s", (now - timedelta(days=2),))
    conn.commit()
    world.customers.update(customer_updates)
    world.prices.update(price_updates)


def safe(conn, func, *args):
    try:
        func(conn, *args)
    except psycopg.Error as exc:
        conn.rollback()
        print(f"Database error in {func.__name__}: {exc}")


def run(conn, args):
    world = load_world(conn)
    if not world.customers:
        raise SystemExit("The database is empty. Run the seed command first.")
    clock = SimClock(datetime.now(timezone.utc) - timedelta(days=args.start_days_ago), args.speedup)
    last_sim = clock.sim_start
    world.last_hour = last_sim.replace(minute=0, second=0, microsecond=0)
    print(f"Starting at {last_sim:%Y-%m-%d %H:%M} UTC, {len(world.heap)} open orders to continue.")

    bar = None
    if not clock.caught_up():
        total = (datetime.now(timezone.utc) - last_sim).total_seconds()
        bar = tqdm(total=total, unit="sim-s", desc="Catching up")
    last_report = time.monotonic()
    try:
        while True:
            started = time.monotonic()
            now = clock.now()
            dt = (now - last_sim).total_seconds()
            if dt > 0:
                expected = args.orders_per_hour * traffic_factor(last_sim + (now - last_sim) / 2) * dt / 3600
                for _ in range(int(expected) + (random.random() < expected - int(expected))):
                    safe(conn, create_order, world, last_sim + timedelta(seconds=random.uniform(0, dt)))
                while world.heap and world.heap[0][0] <= now:
                    due, order_id, status = heapq.heappop(world.heap)
                    safe(conn, process_step, world, due, order_id, status)
                hour = now.replace(minute=0, second=0, microsecond=0)
                if hour > world.last_hour:
                    safe(conn, hourly_maintenance, world, now)
                    world.last_hour = hour
                last_sim = now
                if bar:
                    bar.update(dt)
                    bar.set_postfix(orders=world.stats["orders"])
                    if clock.caught_up():
                        bar.close()
                        bar = None
                        print("Caught up. Running in real time now.")
            if bar is None and time.monotonic() - last_report >= args.report_seconds:
                last_report = time.monotonic()
                print(f"[{now:%Y-%m-%d %H:%M}] orders={world.stats['orders']} steps={world.stats['steps']} "
                      f"lost_sales={world.stats['lost_sales']} open_orders={len(world.heap)}")
            time.sleep(max(0.0, args.tick_seconds - (time.monotonic() - started)))
    except KeyboardInterrupt:
        print("Stopped by user.")
    finally:
        if bar:
            bar.close()


def main():
    parser = argparse.ArgumentParser(description="Order management data generator")
    sub = parser.add_subparsers(dest="command", required=True)
    p_seed = sub.add_parser("seed", help="Create reference data and initial stock")
    p_seed.add_argument("--customers", type=int, default=2000)
    p_seed.add_argument("--products", type=int, default=150)
    p_run = sub.add_parser("run", help="Generate orders and updates until stopped")
    p_run.add_argument("--orders-per-hour", type=float, default=120)
    p_run.add_argument("--start-days-ago", type=float, default=0)
    p_run.add_argument("--speedup", type=float, default=1)
    p_run.add_argument("--tick-seconds", type=float, default=1.0)
    p_run.add_argument("--report-seconds", type=float, default=30)
    p_run.add_argument("--random-seed", type=int, default=None)
    args = parser.parse_args()

    if args.command == "run" and args.random_seed is not None:
        random.seed(args.random_seed)
    with connect() as conn:
        if args.command == "seed":
            seed(conn, args.customers, args.products)
        else:
            run(conn, args)


if __name__ == "__main__":
    main()
