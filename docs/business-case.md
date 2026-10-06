# Business case

## Context

A fictional distributor of food and consumer goods has warehouses in Casablanca,
Tanger and Marrakech. Operations teams follow orders, shipments and stock with
Excel files sent by email. The files arrive late, are often inconsistent, and
nobody can answer simple questions during the day, such as "which orders will be
late today?".

## Goal

Build a data platform that captures every change of the operational database in
near real time and turns it into reliable, documented KPIs.

## KPI definitions

| KPI | Definition |
|---|---|
| On-time delivery rate | Delivered shipments with `delivered_at <= promised_at`, divided by all delivered shipments in the period |
| Average lead time | Average of `delivered_at - order_created_at` for delivered orders |
| Stock-out rate | Share of (product, warehouse) pairs with available quantity equal to 0, at the time of measure |
| Late orders | Orders not delivered whose `promised_at` is in the past |

## Data freshness targets

| Layer | Target |
|---|---|
| Silver | Less than 5 minutes after the change is committed in the source |
| Gold | Less than 15 minutes after the change is committed in the source |

These targets are measured and monitored (see the monitoring step). They are
goals for this project, not guarantees.

## Scope

In scope: customers, products, warehouses, carriers, orders, order items,
shipments and stock movements.

Out of scope for now: payments, returns, route optimization.

## Source data

The source is simulated by a data generator. The data is synthetic, but the
mechanisms (change capture, updates, deletes, late events, bad data) are real.
