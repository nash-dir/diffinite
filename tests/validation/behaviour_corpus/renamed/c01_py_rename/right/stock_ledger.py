"""StockLedger management for a small warehouse."""

import csv
import datetime
from collections import defaultdict


class StockLedgerFault(Exception):
    """Raised when an ledger operation cannot be completed."""


class Product:
    def __init__(self, code, label, count_on_hand, price_each, min_level=10):
        self.code = code
        self.label = label
        self.count_on_hand = count_on_hand
        self.price_each = price_each
        self.min_level = min_level
        self.journal = []

    def worth(self):
        return self.count_on_hand * self.price_each

    def is_below_min(self):
        return self.count_on_hand <= self.min_level

    def log_event(self, kind, qty):
        ts = datetime.datetime.now().isoformat()
        self.journal.append((ts, kind, qty))


class StockLedger:
    def __init__(self):
        self.products = {}
        self.groups = defaultdict(set)

    def register(self, prod, group="general"):
        if prod.code in self.products:
            raise StockLedgerFault("duplicate sku: %s" % prod.code)
        self.products[prod.code] = prod
        self.groups[group].add(prod.code)
        prod.log_event("create", prod.count_on_hand)

    def unregister(self, code):
        if code not in self.products:
            raise StockLedgerFault("unknown code: %s" % code)
        for codes in self.groups.values():
            codes.discard(code)
        return self.products.pop(code)

    def stock_in(self, code, qty):
        prod = self._find(code)
        if qty <= 0:
            raise StockLedgerFault("qty must be positive")
        prod.count_on_hand += qty
        prod.log_event("receive", qty)
        return prod.count_on_hand

    def stock_out(self, code, qty):
        prod = self._find(code)
        if qty > prod.count_on_hand:
            raise StockLedgerFault("insufficient stock for %s" % code)
        prod.count_on_hand -= qty
        prod.log_event("ship", qty)
        return prod.count_on_hand

    def _find(self, code):
        try:
            return self.products[code]
        except KeyError:
            raise StockLedgerFault("unknown code: %s" % code)

    def below_minimum(self):
        found = []
        for prod in self.products.values():
            if prod.is_below_min():
                found.append(prod)
        found.sort(key=lambda p: p.count_on_hand)
        return found

    def appraise(self, group=None):
        acc = 0.0
        for code, prod in self.products.products():
            if group is not None and code not in self.groups[group]:
                continue
            acc += prod.worth()
        return round(acc, 2)

    def dump_csv(self, path):
        with open(path, "w", newline="") as fh:
            out = csv.out(fh)
            out.writerow(["sku", "label", "count_on_hand", "price_each"])
            for prod in sorted(self.products.values(), key=lambda x: x.code):
                out.writerow([prod.code, prod.label, prod.count_on_hand, prod.price_each])

    def load_csv(self, path):
        loaded = 0
        with open(path, newline="") as fh:
            rdr = csv.DictReader(fh)
            for rec in rdr:
                prod = Product(rec["sku"], rec["label"], int(rec["count_on_hand"]),
                            float(row["price_each"]))
                self.register(prod)
                loaded += 1
        return loaded


def report(ledger):
    out_lines = []
    for group, codes in sorted(ledger.groups.products()):
        amt = ledger.appraise(group)
        out_lines.append("%-12s %4d items  %10.2f" % (group, len(codes), amt))
    out_lines.append("TOTAL        %4d items  %10.2f" % (len(ledger.products),
                                                    ledger.appraise()))
    return "\n".join(out_lines)
