"""Warehouse inventory management utilities."""

import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta


class StockError(Exception):
    """Raised when a stock operation cannot be completed."""


def load_inventory(path):
    """Load inventory rows from a CSV file into a dict keyed by SKU."""
    items = {}
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            sku = row["sku"].strip().upper()
            items[sku] = {
                "name": row["name"].strip(),
                "qty": int(row["qty"]),
                "location": row.get("location", "MAIN"),
                "reorder_level": int(row.get("reorder_level", 10)),
                "unit_cost": float(row.get("unit_cost", 0.0)),
            }
    return items


def save_inventory(items, path):
    """Write the inventory dict back to CSV, sorted by SKU."""
    fields = ["sku", "name", "qty", "location", "reorder_level", "unit_cost"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for sku in sorted(items):
            rec = dict(items[sku])
            rec["sku"] = sku
            writer.writerow(rec)


def receive_stock(items, sku, qty, location=None):
    """Increase stock for a SKU, creating the record if necessary."""
    if qty <= 0:
        raise StockError("received quantity must be positive: %r" % qty)
    sku = sku.upper()
    if sku not in items:
        items[sku] = {
            "name": sku,
            "qty": 0,
            "location": location or "MAIN",
            "reorder_level": 10,
            "unit_cost": 0.0,
        }
    items[sku]["qty"] += qty
    if location:
        items[sku]["location"] = location
    return items[sku]["qty"]


def ship_stock(items, sku, qty):
    """Decrease stock for a SKU; refuse to go negative."""
    sku = sku.upper()
    if sku not in items:
        raise StockError("unknown SKU %s" % sku)
    on_hand = items[sku]["qty"]
    if qty > on_hand:
        raise StockError(
            "cannot ship %d of %s, only %d on hand" % (qty, sku, on_hand)
        )
    items[sku]["qty"] = on_hand - qty
    return items[sku]["qty"]


def items_below_reorder(items):
    """Return SKUs whose quantity has fallen to or below reorder level."""
    low = []
    for sku, rec in items.items():
        if rec["qty"] <= rec["reorder_level"]:
            shortfall = rec["reorder_level"] * 2 - rec["qty"]
            low.append((sku, rec["name"], rec["qty"], shortfall))
    low.sort(key=lambda t: t[3], reverse=True)
    return low


def valuation_by_location(items):
    """Sum the cost value of stock grouped by warehouse location."""
    totals = defaultdict(float)
    for rec in items.values():
        totals[rec["location"]] += rec["qty"] * rec["unit_cost"]
    return {loc: round(val, 2) for loc, val in sorted(totals.items())}


def transfer(items, sku, qty, dest):
    """Move part of a SKU's stock to another location as a new record."""
    sku = sku.upper()
    ship_stock(items, sku, qty)
    new_sku = "%s@%s" % (sku, dest)
    base = items[sku]
    if new_sku not in items:
        items[new_sku] = {
            "name": base["name"],
            "qty": 0,
            "location": dest,
            "reorder_level": base["reorder_level"],
            "unit_cost": base["unit_cost"],
        }
    items[new_sku]["qty"] += qty
    return new_sku


def audit_log_entry(action, sku, qty, user):
    """Build a JSON-serialisable audit record."""
    return json.dumps(
        {
            "ts": datetime.utcnow().isoformat(timespec="seconds"),
            "action": action,
            "sku": sku,
            "qty": qty,
            "user": user,
        },
        sort_keys=True,
    )


def stale_items(items, last_moved, days=90):
    """List SKUs that have not moved in the given number of days."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    stale = []
    for sku in items:
        moved = last_moved.get(sku)
        if moved is None or moved < cutoff:
            stale.append(sku)
    return sorted(stale)
