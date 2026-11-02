"""Inventory management for a small warehouse."""

import csv
import datetime
from collections import defaultdict


class InventoryError(Exception):
    """Raised when an inventory operation cannot be completed."""


class Item:
    def __init__(self, sku, name, quantity, unit_price, reorder_level=10):
        self.sku = sku
        self.name = name
        self.quantity = quantity
        self.unit_price = unit_price
        self.reorder_level = reorder_level
        self.history = []

    def total_value(self):
        return self.quantity * self.unit_price

    def needs_reorder(self):
        return self.quantity <= self.reorder_level

    def record(self, action, amount):
        stamp = datetime.datetime.now().isoformat()
        self.history.append((stamp, action, amount))


class Inventory:
    def __init__(self):
        self.items = {}
        self.categories = defaultdict(set)

    def add_item(self, item, category="general"):
        if item.sku in self.items:
            raise InventoryError("duplicate sku: %s" % item.sku)
        self.items[item.sku] = item
        self.categories[category].add(item.sku)
        item.record("create", item.quantity)

    def remove_item(self, sku):
        if sku not in self.items:
            raise InventoryError("unknown sku: %s" % sku)
        for members in self.categories.values():
            members.discard(sku)
        return self.items.pop(sku)

    def receive(self, sku, amount):
        item = self._lookup(sku)
        if amount <= 0:
            raise InventoryError("amount must be positive")
        item.quantity += amount
        item.record("receive", amount)
        return item.quantity

    def ship(self, sku, amount):
        item = self._lookup(sku)
        if amount > item.quantity:
            raise InventoryError("insufficient stock for %s" % sku)
        item.quantity -= amount
        item.record("ship", amount)
        return item.quantity

    def _lookup(self, sku):
        try:
            return self.items[sku]
        except KeyError:
            raise InventoryError("unknown sku: %s" % sku)

    def low_stock(self):
        result = []
        for item in self.items.values():
            if item.needs_reorder():
                result.append(item)
        result.sort(key=lambda entry: entry.quantity)
        return result

    def valuation(self, category=None):
        total = 0.0
        for sku, item in self.items.items():
            if category is not None and sku not in self.categories[category]:
                continue
            total += item.total_value()
        return round(total, 2)

    def export_csv(self, path):
        with open(path, "w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["sku", "name", "quantity", "unit_price"])
            for item in sorted(self.items.values(), key=lambda e: e.sku):
                writer.writerow([item.sku, item.name, item.quantity, item.unit_price])

    def import_csv(self, path):
        count = 0
        with open(path, newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                item = Item(row["sku"], row["name"], int(row["quantity"]),
                            float(row["unit_price"]))
                self.add_item(item)
                count += 1
        return count


def summarize(inventory):
    lines = []
    for category, members in sorted(inventory.categories.items()):
        value = inventory.valuation(category)
        lines.append("%-12s %4d items  %10.2f" % (category, len(members), value))
    lines.append("TOTAL        %4d items  %10.2f" % (len(inventory.items),
                                                    inventory.valuation()))
    return "\n".join(lines)
