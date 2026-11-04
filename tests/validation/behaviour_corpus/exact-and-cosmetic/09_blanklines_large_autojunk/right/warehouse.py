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


import math
import sys
from collections import Counter




class RunningStats:
    """Welford's online algorithm for mean and variance."""


    def __init__(self):

        self.n = 0
        self.mean = 0.0
        self._m2 = 0.0
        self.minimum = math.inf
        self.maximum = -math.inf


    def push(self, x):

        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        self._m2 += delta * (x - self.mean)
        if x < self.minimum:
            self.minimum = x
        if x > self.maximum:
            self.maximum = x


    @property
    def variance(self):

        if self.n < 2:
            return 0.0
        return self._m2 / (self.n - 1)


    @property
    def stdev(self):

        return math.sqrt(self.variance)


    def as_dict(self):

        return {
            "count": self.n,
            "mean": round(self.mean, 6),
            "stdev": round(self.stdev, 6),
            "min": self.minimum if self.n else None,
            "max": self.maximum if self.n else None,
        }




def try_float(text):

    text = text.strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None




def profile(path, delimiter=",", max_categories=10):

    numeric = {}
    categorical = {}
    missing = Counter()
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)
        for row in reader:
            for col, raw in row.items():
                if raw is None or raw.strip() == "":
                    missing[col] += 1
                    continue
                value = try_float(raw)
                if value is not None and col not in categorical:
                    numeric.setdefault(col, RunningStats()).push(value)
                else:
                    numeric.pop(col, None)
                    categorical.setdefault(col, Counter())[raw.strip()] += 1
    report = {}
    for col, stats in numeric.items():
        report[col] = {"type": "numeric", **stats.as_dict(), "missing": missing[col]}
    for col, counts in categorical.items():
        report[col] = {
            "type": "categorical",
            "distinct": len(counts),
            "top": counts.most_common(max_categories),
            "missing": missing[col],
        }
    return report




def render(report, out=sys.stdout):

    for col in sorted(report):
        info = report[col]
        out.write(f"== {col} ({info['type']}) ==\n")
        if info["type"] == "numeric":
            out.write(
                f"  n={info['count']} mean={info['mean']} sd={info['stdev']}"
                f" range=[{info['min']}, {info['max']}]\n"
            )
        else:
            out.write(f"  distinct={info['distinct']}\n")
            for value, count in info["top"]:
                out.write(f"    {value!r}: {count}\n")
        out.write(f"  missing={info['missing']}\n")




def main(argv=None):

    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        sys.stderr.write("usage: csvstats FILE [DELIM]\n")
        return 2
    delim = argv[1] if len(argv) > 1 else ","
    render(profile(argv[0], delimiter=delim))
    return 0




if __name__ == "__main__":
    sys.exit(main())

