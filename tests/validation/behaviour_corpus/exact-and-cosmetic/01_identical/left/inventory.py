"""Warehouse inventory tracking with reorder suggestions."""

from __future__ import annotations

import csv
import datetime as dt
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional


@dataclass
class StockItem:
    sku: str
    name: str
    quantity: int
    reorder_level: int
    unit_cost: float
    supplier: str
    history: List[int] = field(default_factory=list)

    def record(self, delta: int) -> None:
        self.quantity += delta
        self.history.append(delta)
        if self.quantity < 0:
            raise ValueError(f"negative stock for {self.sku}: {self.quantity}")

    @property
    def value(self) -> float:
        return round(self.quantity * self.unit_cost, 2)

    def needs_reorder(self) -> bool:
        return self.quantity <= self.reorder_level


class Inventory:
    def __init__(self) -> None:
        self._items: Dict[str, StockItem] = {}
        self._log: List[tuple] = []

    def add(self, item: StockItem) -> None:
        if item.sku in self._items:
            raise KeyError(f"duplicate sku {item.sku}")
        self._items[item.sku] = item

    def get(self, sku: str) -> Optional[StockItem]:
        return self._items.get(sku)

    def receive(self, sku: str, amount: int) -> None:
        item = self._require(sku)
        item.record(amount)
        self._log.append((dt.datetime.now(), "receive", sku, amount))

    def ship(self, sku: str, amount: int) -> None:
        item = self._require(sku)
        if amount > item.quantity:
            raise ValueError(f"cannot ship {amount} of {sku}; only {item.quantity}")
        item.record(-amount)
        self._log.append((dt.datetime.now(), "ship", sku, amount))

    def _require(self, sku: str) -> StockItem:
        try:
            return self._items[sku]
        except KeyError:
            raise KeyError(f"unknown sku {sku}") from None

    def total_value(self) -> float:
        return round(sum(i.value for i in self._items.values()), 2)

    def reorder_report(self) -> List[dict]:
        rows = []
        for item in sorted(self._items.values(), key=lambda i: i.sku):
            if not item.needs_reorder():
                continue
            shortfall = item.reorder_level * 2 - item.quantity
            rows.append(
                {
                    "sku": item.sku,
                    "name": item.name,
                    "supplier": item.supplier,
                    "order_qty": max(shortfall, 1),
                    "est_cost": round(max(shortfall, 1) * item.unit_cost, 2),
                }
            )
        return rows

    def average_turnover(self, sku: str) -> float:
        item = self._require(sku)
        outgoing = [-d for d in item.history if d < 0]
        if not outgoing:
            return 0.0
        return sum(outgoing) / len(outgoing)

    @classmethod
    def from_csv(cls, path: str) -> "Inventory":
        inv = cls()
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                inv.add(
                    StockItem(
                        sku=row["sku"],
                        name=row["name"],
                        quantity=int(row["quantity"]),
                        reorder_level=int(row["reorder_level"]),
                        unit_cost=float(row["unit_cost"]),
                        supplier=row["supplier"],
                    )
                )
        return inv

    def export_csv(self, path: str, items: Iterable[StockItem] = ()) -> int:
        chosen = list(items) or list(self._items.values())
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["sku", "name", "quantity", "value"])
            for item in chosen:
                writer.writerow([item.sku, item.name, item.quantity, item.value])
        return len(chosen)
