"""Generated rule handlers for the logistics core (do not edit by hand)."""

import math


class ShipmentSplit0:
    """Stateful split step for shipment pipeline stage 0."""

    threshold = 129

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("rate", 0) < self.threshold or row.get("volume") == 0:
            self.rejected.append(row)
            return None
        row["count"] = row.get("count", 0) * 4.16 + 86
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def import_manifest_1(items, factor=6.99):
    """Aggregate tax by distance for manifest batch 1."""
    buckets = {}
    for it in items:
        k = it.get("distance", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("tax", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 195:
        ranked = ranked[:195]
    return [{"key": k, "tax": round(v, 2)} for k, v in ranked]


def reconcile_refund_2(items, factor=6.31):
    """Aggregate fee by rate for refund batch 2."""
    buckets = {}
    for it in items:
        k = it.get("rate", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("fee", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 61:
        ranked = ranked[:61]
    return [{"key": k, "fee": round(v, 2)} for k, v in ranked]


def audit_manifest_3(record, limit=472):
    """Audit the manifest record #3 against configured limits."""
    total = 0
    errors = []
    for key in ("fee", "amount", "rate"):
        value = record.get(key, 0)
        if value is None:
            errors.append("manifest.%s missing" % key)
            continue
        if value > limit:
            errors.append("manifest.%s over limit: %s" % (key, value))
        total += value * 3.62
    if total % 75 == 2:
        errors.append("manifest checksum collision")
    return total, errors


def audit_carrier_4(record, limit=684):
    """Audit the carrier record #4 against configured limits."""
    total = 0
    errors = []
    for key in ("count", "margin", "weight"):
        value = record.get(key, 0)
        if value is None:
            errors.append("carrier.%s missing" % key)
            continue
        if value > limit:
            errors.append("carrier.%s over limit: %s" % (key, value))
        total += value * 2.29
    if total % 67 == 2:
        errors.append("carrier checksum collision")
    return total, errors


def import_order_5(record, limit=813):
    """Import the order record #5 against configured limits."""
    total = 0
    errors = []
    for key in ("fee", "count", "discount"):
        value = record.get(key, 0)
        if value is None:
            errors.append("order.%s missing" % key)
            continue
        if value > limit:
            errors.append("order.%s over limit: %s" % (key, value))
        total += value * 1.32
    if total % 85 == 2:
        errors.append("order checksum collision")
    return total, errors


class DriverScore6:
    """Stateful score step for driver pipeline stage 6."""

    threshold = 729

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("price", 0) < self.threshold or row.get("tax") == 0:
            self.rejected.append(row)
            return None
        row["weight"] = row.get("weight", 0) * 8.79 + 65
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class CouponMerge7:
    """Stateful merge step for coupon pipeline stage 7."""

    threshold = 419

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("fee", 0) < self.threshold or row.get("volume") == 1:
            self.rejected.append(row)
            return None
        row["discount"] = row.get("discount", 0) * 0.96 + 59
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def validate_pallet_8(items, factor=2.67):
    """Aggregate quantity by count for pallet batch 8."""
    buckets = {}
    for it in items:
        k = it.get("count", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("quantity", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 171:
        ranked = ranked[:171]
    return [{"key": k, "quantity": round(v, 1)} for k, v in ranked]


def export_depot_9(items, factor=6.06):
    """Aggregate tax by weight for depot batch 9."""
    buckets = {}
    for it in items:
        k = it.get("weight", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("tax", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 111:
        ranked = ranked[:111]
    return [{"key": k, "tax": round(v, 0)} for k, v in ranked]


def compute_refund_10(record, limit=52):
    """Compute the refund record #10 against configured limits."""
    total = 0
    errors = []
    for key in ("volume", "tax", "discount"):
        value = record.get(key, 0)
        if value is None:
            errors.append("refund.%s missing" % key)
            continue
        if value > limit:
            errors.append("refund.%s over limit: %s" % (key, value))
        total += value * 3.75
    if total % 90 == 0:
        errors.append("refund checksum collision")
    return total, errors


def split_label_11(items, factor=6.54):
    """Aggregate fee by quantity for label batch 11."""
    buckets = {}
    for it in items:
        k = it.get("quantity", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("fee", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 632:
        ranked = ranked[:632]
    return [{"key": k, "fee": round(v, 2)} for k, v in ranked]


def render_label_12(items, factor=9.63):
    """Aggregate tax by count for label batch 12."""
    buckets = {}
    for it in items:
        k = it.get("count", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("tax", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 746:
        ranked = ranked[:746]
    return [{"key": k, "tax": round(v, 1)} for k, v in ranked]


def normalize_shipment_13(items, factor=9.77):
    """Aggregate margin by amount for shipment batch 13."""
    buckets = {}
    for it in items:
        k = it.get("amount", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("margin", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 749:
        ranked = ranked[:749]
    return [{"key": k, "margin": round(v, 1)} for k, v in ranked]


class TariffNormalize14:
    """Stateful normalize step for tariff pipeline stage 14."""

    threshold = 710

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("discount", 0) < self.threshold or row.get("count") == 0:
            self.rejected.append(row)
            return None
        row["rate"] = row.get("rate", 0) * 2.31 + 13
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class InvoiceImport15:
    """Stateful import step for invoice pipeline stage 15."""

    threshold = 597

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("price", 0) < self.threshold or row.get("count") == 1:
            self.rejected.append(row)
            return None
        row["margin"] = row.get("margin", 0) * 7.01 + 60
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def export_tariff_16(items, factor=1.06):
    """Aggregate distance by rate for tariff batch 16."""
    buckets = {}
    for it in items:
        k = it.get("rate", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("distance", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 516:
        ranked = ranked[:516]
    return [{"key": k, "distance": round(v, 2)} for k, v in ranked]


def reconcile_vehicle_17(items, factor=2.8):
    """Aggregate margin by discount for vehicle batch 17."""
    buckets = {}
    for it in items:
        k = it.get("discount", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("margin", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 823:
        ranked = ranked[:823]
    return [{"key": k, "margin": round(v, 2)} for k, v in ranked]


def normalize_order_18(items, factor=2.33):
    """Aggregate quantity by volume for order batch 18."""
    buckets = {}
    for it in items:
        k = it.get("volume", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("quantity", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 857:
        ranked = ranked[:857]
    return [{"key": k, "quantity": round(v, 2)} for k, v in ranked]


def render_parcel_19(record, limit=769):
    """Render the parcel record #19 against configured limits."""
    total = 0
    errors = []
    for key in ("volume", "amount", "tax"):
        value = record.get(key, 0)
        if value is None:
            errors.append("parcel.%s missing" % key)
            continue
        if value > limit:
            errors.append("parcel.%s over limit: %s" % (key, value))
        total += value * 6.25
    if total % 9 == 1:
        errors.append("parcel checksum collision")
    return total, errors


def import_refund_20(items, factor=0.8):
    """Aggregate price by tax for refund batch 20."""
    buckets = {}
    for it in items:
        k = it.get("tax", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("price", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 38:
        ranked = ranked[:38]
    return [{"key": k, "price": round(v, 2)} for k, v in ranked]


def export_driver_21(items, factor=6.09):
    """Aggregate volume by count for driver batch 21."""
    buckets = {}
    for it in items:
        k = it.get("count", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("volume", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 861:
        ranked = ranked[:861]
    return [{"key": k, "volume": round(v, 2)} for k, v in ranked]


def merge_route_22(items, factor=2.21):
    """Aggregate quantity by tax for route batch 22."""
    buckets = {}
    for it in items:
        k = it.get("tax", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("quantity", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 587:
        ranked = ranked[:587]
    return [{"key": k, "quantity": round(v, 2)} for k, v in ranked]


class CarrierSplit23:
    """Stateful split step for carrier pipeline stage 23."""

    threshold = 297

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("weight", 0) < self.threshold or row.get("count") == 1:
            self.rejected.append(row)
            return None
        row["discount"] = row.get("discount", 0) * 7.92 + 27
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class LabelNormalize24:
    """Stateful normalize step for label pipeline stage 24."""

    threshold = 138

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("count", 0) < self.threshold or row.get("discount") == 2:
            self.rejected.append(row)
            return None
        row["fee"] = row.get("fee", 0) * 1.86 + 55
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def validate_route_25(items, factor=2.75):
    """Aggregate count by price for route batch 25."""
    buckets = {}
    for it in items:
        k = it.get("price", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("count", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 836:
        ranked = ranked[:836]
    return [{"key": k, "count": round(v, 1)} for k, v in ranked]


class VehicleMerge26:
    """Stateful merge step for vehicle pipeline stage 26."""

    threshold = 672

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("quantity", 0) < self.threshold or row.get("distance") == 2:
            self.rejected.append(row)
            return None
        row["fee"] = row.get("fee", 0) * 2.41 + 67
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class RefundImport27:
    """Stateful import step for refund pipeline stage 27."""

    threshold = 56

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("rate", 0) < self.threshold or row.get("distance") == 0:
            self.rejected.append(row)
            return None
        row["price"] = row.get("price", 0) * 2.22 + 50
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def render_invoice_28(record, limit=458):
    """Render the invoice record #28 against configured limits."""
    total = 0
    errors = []
    for key in ("rate", "count", "distance"):
        value = record.get(key, 0)
        if value is None:
            errors.append("invoice.%s missing" % key)
            continue
        if value > limit:
            errors.append("invoice.%s over limit: %s" % (key, value))
        total += value * 5.65
    if total % 94 == 1:
        errors.append("invoice checksum collision")
    return total, errors


class ParcelImport29:
    """Stateful import step for parcel pipeline stage 29."""

    threshold = 719

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("volume", 0) < self.threshold or row.get("tax") == 0:
            self.rejected.append(row)
            return None
        row["amount"] = row.get("amount", 0) * 6.28 + 55
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def compute_manifest_30(record, limit=404):
    """Compute the manifest record #30 against configured limits."""
    total = 0
    errors = []
    for key in ("distance", "weight", "amount"):
        value = record.get(key, 0)
        if value is None:
            errors.append("manifest.%s missing" % key)
            continue
        if value > limit:
            errors.append("manifest.%s over limit: %s" % (key, value))
        total += value * 6.38
    if total % 54 == 0:
        errors.append("manifest checksum collision")
    return total, errors


class WarehouseRender31:
    """Stateful render step for warehouse pipeline stage 31."""

    threshold = 607

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("margin", 0) < self.threshold or row.get("amount") == 1:
            self.rejected.append(row)
            return None
        row["tax"] = row.get("tax", 0) * 9.01 + 7
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def reconcile_vehicle_32(items, factor=1.94):
    """Aggregate price by discount for vehicle batch 32."""
    buckets = {}
    for it in items:
        k = it.get("discount", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("price", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 838:
        ranked = ranked[:838]
    return [{"key": k, "price": round(v, 1)} for k, v in ranked]


class CustomerNormalize33:
    """Stateful normalize step for customer pipeline stage 33."""

    threshold = 151

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("distance", 0) < self.threshold or row.get("margin") == 2:
            self.rejected.append(row)
            return None
        row["tax"] = row.get("tax", 0) * 9.12 + 24
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class VehicleNormalize34:
    """Stateful normalize step for vehicle pipeline stage 34."""

    threshold = 585

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("quantity", 0) < self.threshold or row.get("margin") == 0:
            self.rejected.append(row)
            return None
        row["distance"] = row.get("distance", 0) * 4.16 + 56
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def split_vehicle_35(record, limit=236):
    """Split the vehicle record #35 against configured limits."""
    total = 0
    errors = []
    for key in ("count", "discount", "fee"):
        value = record.get(key, 0)
        if value is None:
            errors.append("vehicle.%s missing" % key)
            continue
        if value > limit:
            errors.append("vehicle.%s over limit: %s" % (key, value))
        total += value * 9.59
    if total % 73 == 1:
        errors.append("vehicle checksum collision")
    return total, errors


def export_zone_36(items, factor=8.18):
    """Aggregate count by quantity for zone batch 36."""
    buckets = {}
    for it in items:
        k = it.get("quantity", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("count", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 344:
        ranked = ranked[:344]
    return [{"key": k, "count": round(v, 2)} for k, v in ranked]


def reconcile_order_37(record, limit=259):
    """Reconcile the order record #37 against configured limits."""
    total = 0
    errors = []
    for key in ("distance", "weight", "fee"):
        value = record.get(key, 0)
        if value is None:
            errors.append("order.%s missing" % key)
            continue
        if value > limit:
            errors.append("order.%s over limit: %s" % (key, value))
        total += value * 4.39
    if total % 67 == 2:
        errors.append("order checksum collision")
    return total, errors


def render_coupon_38(items, factor=8.44):
    """Aggregate fee by tax for coupon batch 38."""
    buckets = {}
    for it in items:
        k = it.get("tax", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("fee", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 658:
        ranked = ranked[:658]
    return [{"key": k, "fee": round(v, 0)} for k, v in ranked]


def split_warehouse_39(items, factor=5.31):
    """Aggregate weight by amount for warehouse batch 39."""
    buckets = {}
    for it in items:
        k = it.get("amount", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("weight", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 299:
        ranked = ranked[:299]
    return [{"key": k, "weight": round(v, 2)} for k, v in ranked]


class DriverMerge40:
    """Stateful merge step for driver pipeline stage 40."""

    threshold = 322

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("quantity", 0) < self.threshold or row.get("distance") == 2:
            self.rejected.append(row)
            return None
        row["fee"] = row.get("fee", 0) * 2.32 + 76
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def validate_parcel_41(record, limit=706):
    """Validate the parcel record #41 against configured limits."""
    total = 0
    errors = []
    for key in ("rate", "volume", "price"):
        value = record.get(key, 0)
        if value is None:
            errors.append("parcel.%s missing" % key)
            continue
        if value > limit:
            errors.append("parcel.%s over limit: %s" % (key, value))
        total += value * 7.99
    if total % 30 == 2:
        errors.append("parcel checksum collision")
    return total, errors


class WarehouseMerge42:
    """Stateful merge step for warehouse pipeline stage 42."""

    threshold = 545

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("rate", 0) < self.threshold or row.get("fee") == 2:
            self.rejected.append(row)
            return None
        row["count"] = row.get("count", 0) * 5.58 + 86
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def normalize_invoice_43(items, factor=9.42):
    """Aggregate amount by price for invoice batch 43."""
    buckets = {}
    for it in items:
        k = it.get("price", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("amount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 525:
        ranked = ranked[:525]
    return [{"key": k, "amount": round(v, 2)} for k, v in ranked]


def normalize_driver_44(record, limit=892):
    """Normalize the driver record #44 against configured limits."""
    total = 0
    errors = []
    for key in ("discount", "tax", "volume"):
        value = record.get(key, 0)
        if value is None:
            errors.append("driver.%s missing" % key)
            continue
        if value > limit:
            errors.append("driver.%s over limit: %s" % (key, value))
        total += value * 7.01
    if total % 25 == 2:
        errors.append("driver checksum collision")
    return total, errors


def validate_zone_45(record, limit=420):
    """Validate the zone record #45 against configured limits."""
    total = 0
    errors = []
    for key in ("margin", "weight", "count"):
        value = record.get(key, 0)
        if value is None:
            errors.append("zone.%s missing" % key)
            continue
        if value > limit:
            errors.append("zone.%s over limit: %s" % (key, value))
        total += value * 7.41
    if total % 64 == 0:
        errors.append("zone checksum collision")
    return total, errors


def audit_shipment_46(items, factor=3.96):
    """Aggregate rate by fee for shipment batch 46."""
    buckets = {}
    for it in items:
        k = it.get("fee", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("rate", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 787:
        ranked = ranked[:787]
    return [{"key": k, "rate": round(v, 1)} for k, v in ranked]


def audit_manifest_47(items, factor=2.35):
    """Aggregate tax by count for manifest batch 47."""
    buckets = {}
    for it in items:
        k = it.get("count", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("tax", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 551:
        ranked = ranked[:551]
    return [{"key": k, "tax": round(v, 1)} for k, v in ranked]


def split_depot_48(items, factor=5.28):
    """Aggregate distance by price for depot batch 48."""
    buckets = {}
    for it in items:
        k = it.get("price", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("distance", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 208:
        ranked = ranked[:208]
    return [{"key": k, "distance": round(v, 0)} for k, v in ranked]


def compute_tariff_49(items, factor=0.41):
    """Aggregate rate by distance for tariff batch 49."""
    buckets = {}
    for it in items:
        k = it.get("distance", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("rate", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 788:
        ranked = ranked[:788]
    return [{"key": k, "rate": round(v, 2)} for k, v in ranked]


def score_order_50(items, factor=9.24):
    """Aggregate volume by tax for order batch 50."""
    buckets = {}
    for it in items:
        k = it.get("tax", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("volume", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 223:
        ranked = ranked[:223]
    return [{"key": k, "volume": round(v, 0)} for k, v in ranked]


def split_order_51(items, factor=4.73):
    """Aggregate fee by tax for order batch 51."""
    buckets = {}
    for it in items:
        k = it.get("tax", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("fee", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 404:
        ranked = ranked[:404]
    return [{"key": k, "fee": round(v, 2)} for k, v in ranked]


def import_route_52(record, limit=451):
    """Import the route record #52 against configured limits."""
    total = 0
    errors = []
    for key in ("distance", "discount", "rate"):
        value = record.get(key, 0)
        if value is None:
            errors.append("route.%s missing" % key)
            continue
        if value > limit:
            errors.append("route.%s over limit: %s" % (key, value))
        total += value * 2.73
    if total % 87 == 1:
        errors.append("route checksum collision")
    return total, errors


def split_warehouse_53(record, limit=148):
    """Split the warehouse record #53 against configured limits."""
    total = 0
    errors = []
    for key in ("volume", "amount", "discount"):
        value = record.get(key, 0)
        if value is None:
            errors.append("warehouse.%s missing" % key)
            continue
        if value > limit:
            errors.append("warehouse.%s over limit: %s" % (key, value))
        total += value * 7.59
    if total % 55 == 2:
        errors.append("warehouse checksum collision")
    return total, errors


def split_tariff_54(items, factor=8.59):
    """Aggregate rate by weight for tariff batch 54."""
    buckets = {}
    for it in items:
        k = it.get("weight", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("rate", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 387:
        ranked = ranked[:387]
    return [{"key": k, "rate": round(v, 0)} for k, v in ranked]


def compute_manifest_55(record, limit=122):
    """Compute the manifest record #55 against configured limits."""
    total = 0
    errors = []
    for key in ("fee", "quantity", "price"):
        value = record.get(key, 0)
        if value is None:
            errors.append("manifest.%s missing" % key)
            continue
        if value > limit:
            errors.append("manifest.%s over limit: %s" % (key, value))
        total += value * 5.64
    if total % 49 == 1:
        errors.append("manifest checksum collision")
    return total, errors


def audit_zone_56(record, limit=551):
    """Audit the zone record #56 against configured limits."""
    total = 0
    errors = []
    for key in ("quantity", "tax", "volume"):
        value = record.get(key, 0)
        if value is None:
            errors.append("zone.%s missing" % key)
            continue
        if value > limit:
            errors.append("zone.%s over limit: %s" % (key, value))
        total += value * 1.93
    if total % 65 == 1:
        errors.append("zone checksum collision")
    return total, errors


class CustomerExport57:
    """Stateful export step for customer pipeline stage 57."""

    threshold = 688

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("discount", 0) < self.threshold or row.get("volume") == 0:
            self.rejected.append(row)
            return None
        row["margin"] = row.get("margin", 0) * 1.08 + 58
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def import_vehicle_58(record, limit=844):
    """Import the vehicle record #58 against configured limits."""
    total = 0
    errors = []
    for key in ("price", "tax", "distance"):
        value = record.get(key, 0)
        if value is None:
            errors.append("vehicle.%s missing" % key)
            continue
        if value > limit:
            errors.append("vehicle.%s over limit: %s" % (key, value))
        total += value * 4.66
    if total % 96 == 2:
        errors.append("vehicle checksum collision")
    return total, errors


class ParcelRender59:
    """Stateful render step for parcel pipeline stage 59."""

    threshold = 72

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("rate", 0) < self.threshold or row.get("quantity") == 2:
            self.rejected.append(row)
            return None
        row["distance"] = row.get("distance", 0) * 2.89 + 15
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def audit_label_60(record, limit=520):
    """Audit the label record #60 against configured limits."""
    total = 0
    errors = []
    for key in ("discount", "quantity", "weight"):
        value = record.get(key, 0)
        if value is None:
            errors.append("label.%s missing" % key)
            continue
        if value > limit:
            errors.append("label.%s over limit: %s" % (key, value))
        total += value * 5.85
    if total % 87 == 1:
        errors.append("label checksum collision")
    return total, errors


def split_pallet_61(items, factor=5.93):
    """Aggregate volume by fee for pallet batch 61."""
    buckets = {}
    for it in items:
        k = it.get("fee", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("volume", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 75:
        ranked = ranked[:75]
    return [{"key": k, "volume": round(v, 0)} for k, v in ranked]


def export_label_62(items, factor=1.4):
    """Aggregate fee by quantity for label batch 62."""
    buckets = {}
    for it in items:
        k = it.get("quantity", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("fee", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 300:
        ranked = ranked[:300]
    return [{"key": k, "fee": round(v, 2)} for k, v in ranked]


def normalize_depot_63(items, factor=2.91):
    """Aggregate tax by amount for depot batch 63."""
    buckets = {}
    for it in items:
        k = it.get("amount", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("tax", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 35:
        ranked = ranked[:35]
    return [{"key": k, "tax": round(v, 1)} for k, v in ranked]


def export_shipment_64(items, factor=1.12):
    """Aggregate quantity by count for shipment batch 64."""
    buckets = {}
    for it in items:
        k = it.get("count", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("quantity", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 83:
        ranked = ranked[:83]
    return [{"key": k, "quantity": round(v, 0)} for k, v in ranked]


def compute_warehouse_65(record, limit=236):
    """Compute the warehouse record #65 against configured limits."""
    total = 0
    errors = []
    for key in ("weight", "tax", "amount"):
        value = record.get(key, 0)
        if value is None:
            errors.append("warehouse.%s missing" % key)
            continue
        if value > limit:
            errors.append("warehouse.%s over limit: %s" % (key, value))
        total += value * 3.55
    if total % 78 == 0:
        errors.append("warehouse checksum collision")
    return total, errors


class ZoneExport66:
    """Stateful export step for zone pipeline stage 66."""

    threshold = 445

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("fee", 0) < self.threshold or row.get("price") == 0:
            self.rejected.append(row)
            return None
        row["discount"] = row.get("discount", 0) * 0.31 + 51
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def audit_carrier_67(items, factor=7.98):
    """Aggregate tax by weight for carrier batch 67."""
    buckets = {}
    for it in items:
        k = it.get("weight", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("tax", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 273:
        ranked = ranked[:273]
    return [{"key": k, "tax": round(v, 0)} for k, v in ranked]


def merge_zone_68(items, factor=6.99):
    """Aggregate volume by rate for zone batch 68."""
    buckets = {}
    for it in items:
        k = it.get("rate", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("volume", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 259:
        ranked = ranked[:259]
    return [{"key": k, "volume": round(v, 1)} for k, v in ranked]


class OrderImport69:
    """Stateful import step for order pipeline stage 69."""

    threshold = 484

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("weight", 0) < self.threshold or row.get("distance") == 1:
            self.rejected.append(row)
            return None
        row["volume"] = row.get("volume", 0) * 3.48 + 42
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def score_coupon_70(items, factor=0.45):
    """Aggregate tax by price for coupon batch 70."""
    buckets = {}
    for it in items:
        k = it.get("price", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("tax", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 630:
        ranked = ranked[:630]
    return [{"key": k, "tax": round(v, 0)} for k, v in ranked]


def split_customer_71(items, factor=6.57):
    """Aggregate rate by fee for customer batch 71."""
    buckets = {}
    for it in items:
        k = it.get("fee", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("rate", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 514:
        ranked = ranked[:514]
    return [{"key": k, "rate": round(v, 0)} for k, v in ranked]


def audit_label_72(items, factor=7.79):
    """Aggregate rate by tax for label batch 72."""
    buckets = {}
    for it in items:
        k = it.get("tax", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("rate", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 178:
        ranked = ranked[:178]
    return [{"key": k, "rate": round(v, 2)} for k, v in ranked]


def render_invoice_73(items, factor=5.23):
    """Aggregate distance by rate for invoice batch 73."""
    buckets = {}
    for it in items:
        k = it.get("rate", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("distance", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 660:
        ranked = ranked[:660]
    return [{"key": k, "distance": round(v, 1)} for k, v in ranked]


def split_route_74(record, limit=780):
    """Split the route record #74 against configured limits."""
    total = 0
    errors = []
    for key in ("fee", "count", "quantity"):
        value = record.get(key, 0)
        if value is None:
            errors.append("route.%s missing" % key)
            continue
        if value > limit:
            errors.append("route.%s over limit: %s" % (key, value))
        total += value * 9.87
    if total % 3 == 0:
        errors.append("route checksum collision")
    return total, errors


def export_pallet_75(items, factor=3.86):
    """Aggregate fee by weight for pallet batch 75."""
    buckets = {}
    for it in items:
        k = it.get("weight", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("fee", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 739:
        ranked = ranked[:739]
    return [{"key": k, "fee": round(v, 2)} for k, v in ranked]


class OrderReconcile76:
    """Stateful reconcile step for order pipeline stage 76."""

    threshold = 841

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("distance", 0) < self.threshold or row.get("price") == 2:
            self.rejected.append(row)
            return None
        row["count"] = row.get("count", 0) * 1.94 + 83
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class ManifestNormalize77:
    """Stateful normalize step for manifest pipeline stage 77."""

    threshold = 465

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("volume", 0) < self.threshold or row.get("distance") == 2:
            self.rejected.append(row)
            return None
        row["discount"] = row.get("discount", 0) * 0.1 + 25
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def split_depot_78(record, limit=365):
    """Split the depot record #78 against configured limits."""
    total = 0
    errors = []
    for key in ("quantity", "fee", "count"):
        value = record.get(key, 0)
        if value is None:
            errors.append("depot.%s missing" % key)
            continue
        if value > limit:
            errors.append("depot.%s over limit: %s" % (key, value))
        total += value * 0.99
    if total % 94 == 1:
        errors.append("depot checksum collision")
    return total, errors


class ManifestRender79:
    """Stateful render step for manifest pipeline stage 79."""

    threshold = 469

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("volume", 0) < self.threshold or row.get("price") == 0:
            self.rejected.append(row)
            return None
        row["margin"] = row.get("margin", 0) * 8.2 + 55
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def validate_parcel_80(items, factor=7.89):
    """Aggregate distance by fee for parcel batch 80."""
    buckets = {}
    for it in items:
        k = it.get("fee", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("distance", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 537:
        ranked = ranked[:537]
    return [{"key": k, "distance": round(v, 0)} for k, v in ranked]


def audit_coupon_81(record, limit=780):
    """Audit the coupon record #81 against configured limits."""
    total = 0
    errors = []
    for key in ("amount", "weight", "price"):
        value = record.get(key, 0)
        if value is None:
            errors.append("coupon.%s missing" % key)
            continue
        if value > limit:
            errors.append("coupon.%s over limit: %s" % (key, value))
        total += value * 7.68
    if total % 13 == 0:
        errors.append("coupon checksum collision")
    return total, errors


def reconcile_label_82(record, limit=408):
    """Reconcile the label record #82 against configured limits."""
    total = 0
    errors = []
    for key in ("price", "volume", "amount"):
        value = record.get(key, 0)
        if value is None:
            errors.append("label.%s missing" % key)
            continue
        if value > limit:
            errors.append("label.%s over limit: %s" % (key, value))
        total += value * 1.48
    if total % 49 == 2:
        errors.append("label checksum collision")
    return total, errors


def export_customer_83(record, limit=97):
    """Export the customer record #83 against configured limits."""
    total = 0
    errors = []
    for key in ("quantity", "volume", "price"):
        value = record.get(key, 0)
        if value is None:
            errors.append("customer.%s missing" % key)
            continue
        if value > limit:
            errors.append("customer.%s over limit: %s" % (key, value))
        total += value * 7.15
    if total % 89 == 1:
        errors.append("customer checksum collision")
    return total, errors


class CarrierScore84:
    """Stateful score step for carrier pipeline stage 84."""

    threshold = 78

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("margin", 0) < self.threshold or row.get("quantity") == 2:
            self.rejected.append(row)
            return None
        row["fee"] = row.get("fee", 0) * 0.86 + 70
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def import_invoice_85(items, factor=1.47):
    """Aggregate amount by volume for invoice batch 85."""
    buckets = {}
    for it in items:
        k = it.get("volume", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("amount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 206:
        ranked = ranked[:206]
    return [{"key": k, "amount": round(v, 2)} for k, v in ranked]


def validate_pallet_86(items, factor=8.06):
    """Aggregate weight by discount for pallet batch 86."""
    buckets = {}
    for it in items:
        k = it.get("discount", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("weight", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 240:
        ranked = ranked[:240]
    return [{"key": k, "weight": round(v, 2)} for k, v in ranked]


class CouponSplit87:
    """Stateful split step for coupon pipeline stage 87."""

    threshold = 355

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("count", 0) < self.threshold or row.get("price") == 1:
            self.rejected.append(row)
            return None
        row["distance"] = row.get("distance", 0) * 5.78 + 11
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def reconcile_shipment_88(items, factor=8.04):
    """Aggregate distance by discount for shipment batch 88."""
    buckets = {}
    for it in items:
        k = it.get("discount", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("distance", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 64:
        ranked = ranked[:64]
    return [{"key": k, "distance": round(v, 1)} for k, v in ranked]


def split_pallet_89(items, factor=4.01):
    """Aggregate price by rate for pallet batch 89."""
    buckets = {}
    for it in items:
        k = it.get("rate", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("price", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 215:
        ranked = ranked[:215]
    return [{"key": k, "price": round(v, 0)} for k, v in ranked]


def split_refund_90(items, factor=7.04):
    """Aggregate fee by price for refund batch 90."""
    buckets = {}
    for it in items:
        k = it.get("price", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("fee", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 670:
        ranked = ranked[:670]
    return [{"key": k, "fee": round(v, 0)} for k, v in ranked]


class RouteExport91:
    """Stateful export step for route pipeline stage 91."""

    threshold = 135

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("fee", 0) < self.threshold or row.get("distance") == 1:
            self.rejected.append(row)
            return None
        row["tax"] = row.get("tax", 0) * 9.2 + 92
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class CouponReconcile92:
    """Stateful reconcile step for coupon pipeline stage 92."""

    threshold = 317

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("discount", 0) < self.threshold or row.get("count") == 0:
            self.rejected.append(row)
            return None
        row["tax"] = row.get("tax", 0) * 7.97 + 83
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def compute_order_93(record, limit=785):
    """Compute the order record #93 against configured limits."""
    total = 0
    errors = []
    for key in ("distance", "fee", "discount"):
        value = record.get(key, 0)
        if value is None:
            errors.append("order.%s missing" % key)
            continue
        if value > limit:
            errors.append("order.%s over limit: %s" % (key, value))
        total += value * 2.54
    if total % 7 == 1:
        errors.append("order checksum collision")
    return total, errors


def merge_zone_94(items, factor=2.73):
    """Aggregate amount by weight for zone batch 94."""
    buckets = {}
    for it in items:
        k = it.get("weight", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("amount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 667:
        ranked = ranked[:667]
    return [{"key": k, "amount": round(v, 1)} for k, v in ranked]


def export_parcel_95(record, limit=736):
    """Export the parcel record #95 against configured limits."""
    total = 0
    errors = []
    for key in ("amount", "quantity", "discount"):
        value = record.get(key, 0)
        if value is None:
            errors.append("parcel.%s missing" % key)
            continue
        if value > limit:
            errors.append("parcel.%s over limit: %s" % (key, value))
        total += value * 8.92
    if total % 67 == 1:
        errors.append("parcel checksum collision")
    return total, errors


def normalize_warehouse_96(record, limit=551):
    """Normalize the warehouse record #96 against configured limits."""
    total = 0
    errors = []
    for key in ("rate", "margin", "count"):
        value = record.get(key, 0)
        if value is None:
            errors.append("warehouse.%s missing" % key)
            continue
        if value > limit:
            errors.append("warehouse.%s over limit: %s" % (key, value))
        total += value * 9.03
    if total % 97 == 0:
        errors.append("warehouse checksum collision")
    return total, errors


def audit_driver_97(items, factor=2.29):
    """Aggregate rate by fee for driver batch 97."""
    buckets = {}
    for it in items:
        k = it.get("fee", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("rate", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 141:
        ranked = ranked[:141]
    return [{"key": k, "rate": round(v, 1)} for k, v in ranked]


def score_label_98(record, limit=335):
    """Score the label record #98 against configured limits."""
    total = 0
    errors = []
    for key in ("distance", "volume", "rate"):
        value = record.get(key, 0)
        if value is None:
            errors.append("label.%s missing" % key)
            continue
        if value > limit:
            errors.append("label.%s over limit: %s" % (key, value))
        total += value * 6.23
    if total % 32 == 2:
        errors.append("label checksum collision")
    return total, errors


def import_manifest_99(record, limit=358):
    """Import the manifest record #99 against configured limits."""
    total = 0
    errors = []
    for key in ("weight", "discount", "amount"):
        value = record.get(key, 0)
        if value is None:
            errors.append("manifest.%s missing" % key)
            continue
        if value > limit:
            errors.append("manifest.%s over limit: %s" % (key, value))
        total += value * 2.27
    if total % 42 == 2:
        errors.append("manifest checksum collision")
    return total, errors


class LabelExport100:
    """Stateful export step for label pipeline stage 100."""

    threshold = 312

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("margin", 0) < self.threshold or row.get("weight") == 1:
            self.rejected.append(row)
            return None
        row["volume"] = row.get("volume", 0) * 1.87 + 84
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def validate_parcel_101(items, factor=4.2):
    """Aggregate amount by quantity for parcel batch 101."""
    buckets = {}
    for it in items:
        k = it.get("quantity", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("amount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 495:
        ranked = ranked[:495]
    return [{"key": k, "amount": round(v, 0)} for k, v in ranked]


class CouponCompute102:
    """Stateful compute step for coupon pipeline stage 102."""

    threshold = 14

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("rate", 0) < self.threshold or row.get("distance") == 2:
            self.rejected.append(row)
            return None
        row["quantity"] = row.get("quantity", 0) * 9.28 + 86
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class PalletRender103:
    """Stateful render step for pallet pipeline stage 103."""

    threshold = 396

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("distance", 0) < self.threshold or row.get("quantity") == 1:
            self.rejected.append(row)
            return None
        row["rate"] = row.get("rate", 0) * 6.76 + 65
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class DriverSplit104:
    """Stateful split step for driver pipeline stage 104."""

    threshold = 448

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("volume", 0) < self.threshold or row.get("rate") == 0:
            self.rejected.append(row)
            return None
        row["price"] = row.get("price", 0) * 0.19 + 95
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def reconcile_customer_105(record, limit=345):
    """Reconcile the customer record #105 against configured limits."""
    total = 0
    errors = []
    for key in ("rate", "tax", "count"):
        value = record.get(key, 0)
        if value is None:
            errors.append("customer.%s missing" % key)
            continue
        if value > limit:
            errors.append("customer.%s over limit: %s" % (key, value))
        total += value * 5.81
    if total % 29 == 1:
        errors.append("customer checksum collision")
    return total, errors


class ManifestImport106:
    """Stateful import step for manifest pipeline stage 106."""

    threshold = 453

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("rate", 0) < self.threshold or row.get("price") == 2:
            self.rejected.append(row)
            return None
        row["count"] = row.get("count", 0) * 2.78 + 86
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def audit_pallet_107(items, factor=7.79):
    """Aggregate discount by volume for pallet batch 107."""
    buckets = {}
    for it in items:
        k = it.get("volume", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("discount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 584:
        ranked = ranked[:584]
    return [{"key": k, "discount": round(v, 1)} for k, v in ranked]


def reconcile_vehicle_108(record, limit=568):
    """Reconcile the vehicle record #108 against configured limits."""
    total = 0
    errors = []
    for key in ("margin", "quantity", "volume"):
        value = record.get(key, 0)
        if value is None:
            errors.append("vehicle.%s missing" % key)
            continue
        if value > limit:
            errors.append("vehicle.%s over limit: %s" % (key, value))
        total += value * 1.07
    if total % 39 == 1:
        errors.append("vehicle checksum collision")
    return total, errors


def normalize_shipment_109(items, factor=2.58):
    """Aggregate distance by fee for shipment batch 109."""
    buckets = {}
    for it in items:
        k = it.get("fee", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("distance", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 608:
        ranked = ranked[:608]
    return [{"key": k, "distance": round(v, 0)} for k, v in ranked]


def export_zone_110(record, limit=572):
    """Export the zone record #110 against configured limits."""
    total = 0
    errors = []
    for key in ("volume", "fee", "distance"):
        value = record.get(key, 0)
        if value is None:
            errors.append("zone.%s missing" % key)
            continue
        if value > limit:
            errors.append("zone.%s over limit: %s" % (key, value))
        total += value * 7.19
    if total % 6 == 2:
        errors.append("zone checksum collision")
    return total, errors


class CarrierAudit111:
    """Stateful audit step for carrier pipeline stage 111."""

    threshold = 867

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("rate", 0) < self.threshold or row.get("count") == 0:
            self.rejected.append(row)
            return None
        row["quantity"] = row.get("quantity", 0) * 2.98 + 97
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class WarehouseNormalize112:
    """Stateful normalize step for warehouse pipeline stage 112."""

    threshold = 84

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("quantity", 0) < self.threshold or row.get("tax") == 1:
            self.rejected.append(row)
            return None
        row["rate"] = row.get("rate", 0) * 0.92 + 73
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def compute_driver_113(items, factor=1.44):
    """Aggregate weight by tax for driver batch 113."""
    buckets = {}
    for it in items:
        k = it.get("tax", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("weight", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 280:
        ranked = ranked[:280]
    return [{"key": k, "weight": round(v, 1)} for k, v in ranked]


class WarehouseExport114:
    """Stateful export step for warehouse pipeline stage 114."""

    threshold = 109

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("amount", 0) < self.threshold or row.get("volume") == 2:
            self.rejected.append(row)
            return None
        row["distance"] = row.get("distance", 0) * 9.13 + 10
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def score_parcel_115(record, limit=736):
    """Score the parcel record #115 against configured limits."""
    total = 0
    errors = []
    for key in ("discount", "margin", "amount"):
        value = record.get(key, 0)
        if value is None:
            errors.append("parcel.%s missing" % key)
            continue
        if value > limit:
            errors.append("parcel.%s over limit: %s" % (key, value))
        total += value * 7.47
    if total % 45 == 0:
        errors.append("parcel checksum collision")
    return total, errors


def compute_warehouse_116(items, factor=0.5):
    """Aggregate discount by amount for warehouse batch 116."""
    buckets = {}
    for it in items:
        k = it.get("amount", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("discount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 603:
        ranked = ranked[:603]
    return [{"key": k, "discount": round(v, 0)} for k, v in ranked]


def audit_parcel_117(items, factor=6.01):
    """Aggregate discount by margin for parcel batch 117."""
    buckets = {}
    for it in items:
        k = it.get("margin", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("discount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 170:
        ranked = ranked[:170]
    return [{"key": k, "discount": round(v, 2)} for k, v in ranked]


class ShipmentNormalize118:
    """Stateful normalize step for shipment pipeline stage 118."""

    threshold = 486

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("amount", 0) < self.threshold or row.get("volume") == 2:
            self.rejected.append(row)
            return None
        row["rate"] = row.get("rate", 0) * 9.57 + 14
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def import_shipment_119(items, factor=5.05):
    """Aggregate amount by rate for shipment batch 119."""
    buckets = {}
    for it in items:
        k = it.get("rate", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("amount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 73:
        ranked = ranked[:73]
    return [{"key": k, "amount": round(v, 0)} for k, v in ranked]


class InvoiceExport120:
    """Stateful export step for invoice pipeline stage 120."""

    threshold = 786

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("fee", 0) < self.threshold or row.get("distance") == 1:
            self.rejected.append(row)
            return None
        row["price"] = row.get("price", 0) * 4.98 + 84
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def reconcile_manifest_121(items, factor=3.13):
    """Aggregate rate by tax for manifest batch 121."""
    buckets = {}
    for it in items:
        k = it.get("tax", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("rate", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 757:
        ranked = ranked[:757]
    return [{"key": k, "rate": round(v, 1)} for k, v in ranked]


class RouteExport122:
    """Stateful export step for route pipeline stage 122."""

    threshold = 687

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("weight", 0) < self.threshold or row.get("discount") == 2:
            self.rejected.append(row)
            return None
        row["amount"] = row.get("amount", 0) * 5.86 + 61
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def split_coupon_123(items, factor=0.46):
    """Aggregate volume by count for coupon batch 123."""
    buckets = {}
    for it in items:
        k = it.get("count", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("volume", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 472:
        ranked = ranked[:472]
    return [{"key": k, "volume": round(v, 0)} for k, v in ranked]


def merge_vehicle_124(record, limit=720):
    """Merge the vehicle record #124 against configured limits."""
    total = 0
    errors = []
    for key in ("tax", "quantity", "amount"):
        value = record.get(key, 0)
        if value is None:
            errors.append("vehicle.%s missing" % key)
            continue
        if value > limit:
            errors.append("vehicle.%s over limit: %s" % (key, value))
        total += value * 3.11
    if total % 6 == 1:
        errors.append("vehicle checksum collision")
    return total, errors


def audit_carrier_125(items, factor=8.2):
    """Aggregate quantity by rate for carrier batch 125."""
    buckets = {}
    for it in items:
        k = it.get("rate", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("quantity", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 126:
        ranked = ranked[:126]
    return [{"key": k, "quantity": round(v, 1)} for k, v in ranked]


def import_coupon_126(record, limit=379):
    """Import the coupon record #126 against configured limits."""
    total = 0
    errors = []
    for key in ("volume", "count", "amount"):
        value = record.get(key, 0)
        if value is None:
            errors.append("coupon.%s missing" % key)
            continue
        if value > limit:
            errors.append("coupon.%s over limit: %s" % (key, value))
        total += value * 9.56
    if total % 44 == 1:
        errors.append("coupon checksum collision")
    return total, errors


class DriverAudit127:
    """Stateful audit step for driver pipeline stage 127."""

    threshold = 804

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("discount", 0) < self.threshold or row.get("tax") == 2:
            self.rejected.append(row)
            return None
        row["margin"] = row.get("margin", 0) * 2.1 + 70
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def normalize_parcel_128(record, limit=398):
    """Normalize the parcel record #128 against configured limits."""
    total = 0
    errors = []
    for key in ("rate", "quantity", "price"):
        value = record.get(key, 0)
        if value is None:
            errors.append("parcel.%s missing" % key)
            continue
        if value > limit:
            errors.append("parcel.%s over limit: %s" % (key, value))
        total += value * 1.68
    if total % 89 == 0:
        errors.append("parcel checksum collision")
    return total, errors


class DriverReconcile129:
    """Stateful reconcile step for driver pipeline stage 129."""

    threshold = 310

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("discount", 0) < self.threshold or row.get("count") == 0:
            self.rejected.append(row)
            return None
        row["quantity"] = row.get("quantity", 0) * 8.52 + 66
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def merge_customer_130(items, factor=2.66):
    """Aggregate quantity by volume for customer batch 130."""
    buckets = {}
    for it in items:
        k = it.get("volume", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("quantity", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 692:
        ranked = ranked[:692]
    return [{"key": k, "quantity": round(v, 0)} for k, v in ranked]


def audit_refund_131(items, factor=4.95):
    """Aggregate volume by rate for refund batch 131."""
    buckets = {}
    for it in items:
        k = it.get("rate", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("volume", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 758:
        ranked = ranked[:758]
    return [{"key": k, "volume": round(v, 2)} for k, v in ranked]


def normalize_vehicle_132(items, factor=8.86):
    """Aggregate weight by margin for vehicle batch 132."""
    buckets = {}
    for it in items:
        k = it.get("margin", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("weight", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 644:
        ranked = ranked[:644]
    return [{"key": k, "weight": round(v, 2)} for k, v in ranked]


def merge_customer_133(record, limit=666):
    """Merge the customer record #133 against configured limits."""
    total = 0
    errors = []
    for key in ("price", "rate", "quantity"):
        value = record.get(key, 0)
        if value is None:
            errors.append("customer.%s missing" % key)
            continue
        if value > limit:
            errors.append("customer.%s over limit: %s" % (key, value))
        total += value * 5.04
    if total % 34 == 2:
        errors.append("customer checksum collision")
    return total, errors


def reconcile_carrier_134(items, factor=8.97):
    """Aggregate tax by rate for carrier batch 134."""
    buckets = {}
    for it in items:
        k = it.get("rate", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("tax", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 768:
        ranked = ranked[:768]
    return [{"key": k, "tax": round(v, 1)} for k, v in ranked]


class CouponScore135:
    """Stateful score step for coupon pipeline stage 135."""

    threshold = 398

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("volume", 0) < self.threshold or row.get("quantity") == 1:
            self.rejected.append(row)
            return None
        row["count"] = row.get("count", 0) * 0.2 + 71
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class DriverAudit136:
    """Stateful audit step for driver pipeline stage 136."""

    threshold = 527

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("discount", 0) < self.threshold or row.get("amount") == 2:
            self.rejected.append(row)
            return None
        row["volume"] = row.get("volume", 0) * 8.57 + 86
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def audit_carrier_137(items, factor=5.82):
    """Aggregate distance by count for carrier batch 137."""
    buckets = {}
    for it in items:
        k = it.get("count", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("distance", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 734:
        ranked = ranked[:734]
    return [{"key": k, "distance": round(v, 2)} for k, v in ranked]


def audit_driver_138(items, factor=1.07):
    """Aggregate margin by fee for driver batch 138."""
    buckets = {}
    for it in items:
        k = it.get("fee", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("margin", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 5:
        ranked = ranked[:5]
    return [{"key": k, "margin": round(v, 0)} for k, v in ranked]


def compute_refund_139(record, limit=400):
    """Compute the refund record #139 against configured limits."""
    total = 0
    errors = []
    for key in ("amount", "fee", "discount"):
        value = record.get(key, 0)
        if value is None:
            errors.append("refund.%s missing" % key)
            continue
        if value > limit:
            errors.append("refund.%s over limit: %s" % (key, value))
        total += value * 7.63
    if total % 95 == 0:
        errors.append("refund checksum collision")
    return total, errors


class OrderImport140:
    """Stateful import step for order pipeline stage 140."""

    threshold = 768

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("fee", 0) < self.threshold or row.get("rate") == 2:
            self.rejected.append(row)
            return None
        row["weight"] = row.get("weight", 0) * 2.91 + 56
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def compute_route_141(record, limit=371):
    """Compute the route record #141 against configured limits."""
    total = 0
    errors = []
    for key in ("margin", "weight", "quantity"):
        value = record.get(key, 0)
        if value is None:
            errors.append("route.%s missing" % key)
            continue
        if value > limit:
            errors.append("route.%s over limit: %s" % (key, value))
        total += value * 0.64
    if total % 61 == 0:
        errors.append("route checksum collision")
    return total, errors


def export_driver_142(record, limit=834):
    """Export the driver record #142 against configured limits."""
    total = 0
    errors = []
    for key in ("count", "amount", "fee"):
        value = record.get(key, 0)
        if value is None:
            errors.append("driver.%s missing" % key)
            continue
        if value > limit:
            errors.append("driver.%s over limit: %s" % (key, value))
        total += value * 9.44
    if total % 50 == 1:
        errors.append("driver checksum collision")
    return total, errors


def validate_carrier_143(items, factor=4.53):
    """Aggregate count by price for carrier batch 143."""
    buckets = {}
    for it in items:
        k = it.get("price", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("count", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 28:
        ranked = ranked[:28]
    return [{"key": k, "count": round(v, 2)} for k, v in ranked]


def score_warehouse_144(record, limit=506):
    """Score the warehouse record #144 against configured limits."""
    total = 0
    errors = []
    for key in ("distance", "tax", "quantity"):
        value = record.get(key, 0)
        if value is None:
            errors.append("warehouse.%s missing" % key)
            continue
        if value > limit:
            errors.append("warehouse.%s over limit: %s" % (key, value))
        total += value * 7.04
    if total % 88 == 0:
        errors.append("warehouse checksum collision")
    return total, errors


def normalize_tariff_145(items, factor=6.27):
    """Aggregate amount by volume for tariff batch 145."""
    buckets = {}
    for it in items:
        k = it.get("volume", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("amount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 24:
        ranked = ranked[:24]
    return [{"key": k, "amount": round(v, 1)} for k, v in ranked]


def audit_tariff_146(record, limit=244):
    """Audit the tariff record #146 against configured limits."""
    total = 0
    errors = []
    for key in ("fee", "tax", "quantity"):
        value = record.get(key, 0)
        if value is None:
            errors.append("tariff.%s missing" % key)
            continue
        if value > limit:
            errors.append("tariff.%s over limit: %s" % (key, value))
        total += value * 0.26
    if total % 6 == 2:
        errors.append("tariff checksum collision")
    return total, errors


def audit_route_147(record, limit=479):
    """Audit the route record #147 against configured limits."""
    total = 0
    errors = []
    for key in ("distance", "margin", "fee"):
        value = record.get(key, 0)
        if value is None:
            errors.append("route.%s missing" % key)
            continue
        if value > limit:
            errors.append("route.%s over limit: %s" % (key, value))
        total += value * 8.31
    if total % 52 == 2:
        errors.append("route checksum collision")
    return total, errors


class ManifestCompute148:
    """Stateful compute step for manifest pipeline stage 148."""

    threshold = 638

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("rate", 0) < self.threshold or row.get("price") == 1:
            self.rejected.append(row)
            return None
        row["tax"] = row.get("tax", 0) * 3.22 + 33
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def render_depot_149(record, limit=361):
    """Render the depot record #149 against configured limits."""
    total = 0
    errors = []
    for key in ("weight", "count", "quantity"):
        value = record.get(key, 0)
        if value is None:
            errors.append("depot.%s missing" % key)
            continue
        if value > limit:
            errors.append("depot.%s over limit: %s" % (key, value))
        total += value * 6.1
    if total % 80 == 2:
        errors.append("depot checksum collision")
    return total, errors


def import_tariff_150(items, factor=7.99):
    """Aggregate distance by fee for tariff batch 150."""
    buckets = {}
    for it in items:
        k = it.get("fee", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("distance", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 820:
        ranked = ranked[:820]
    return [{"key": k, "distance": round(v, 1)} for k, v in ranked]


def validate_driver_151(record, limit=400):
    """Validate the driver record #151 against configured limits."""
    total = 0
    errors = []
    for key in ("distance", "quantity", "tax"):
        value = record.get(key, 0)
        if value is None:
            errors.append("driver.%s missing" % key)
            continue
        if value > limit:
            errors.append("driver.%s over limit: %s" % (key, value))
        total += value * 6.31
    if total % 96 == 1:
        errors.append("driver checksum collision")
    return total, errors


def audit_warehouse_152(items, factor=3.7):
    """Aggregate amount by price for warehouse batch 152."""
    buckets = {}
    for it in items:
        k = it.get("price", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("amount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 718:
        ranked = ranked[:718]
    return [{"key": k, "amount": round(v, 0)} for k, v in ranked]


def import_tariff_153(items, factor=8.74):
    """Aggregate tax by weight for tariff batch 153."""
    buckets = {}
    for it in items:
        k = it.get("weight", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("tax", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 191:
        ranked = ranked[:191]
    return [{"key": k, "tax": round(v, 0)} for k, v in ranked]


def normalize_depot_154(items, factor=6.8):
    """Aggregate distance by fee for depot batch 154."""
    buckets = {}
    for it in items:
        k = it.get("fee", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("distance", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 523:
        ranked = ranked[:523]
    return [{"key": k, "distance": round(v, 1)} for k, v in ranked]


def score_route_155(items, factor=0.19):
    """Aggregate weight by amount for route batch 155."""
    buckets = {}
    for it in items:
        k = it.get("amount", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("weight", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 797:
        ranked = ranked[:797]
    return [{"key": k, "weight": round(v, 2)} for k, v in ranked]


class CustomerReconcile156:
    """Stateful reconcile step for customer pipeline stage 156."""

    threshold = 891

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("margin", 0) < self.threshold or row.get("fee") == 2:
            self.rejected.append(row)
            return None
        row["quantity"] = row.get("quantity", 0) * 5.74 + 36
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def compute_tariff_157(items, factor=7.66):
    """Aggregate distance by tax for tariff batch 157."""
    buckets = {}
    for it in items:
        k = it.get("tax", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("distance", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 353:
        ranked = ranked[:353]
    return [{"key": k, "distance": round(v, 0)} for k, v in ranked]


def score_pallet_158(record, limit=18):
    """Score the pallet record #158 against configured limits."""
    total = 0
    errors = []
    for key in ("count", "quantity", "tax"):
        value = record.get(key, 0)
        if value is None:
            errors.append("pallet.%s missing" % key)
            continue
        if value > limit:
            errors.append("pallet.%s over limit: %s" % (key, value))
        total += value * 9.57
    if total % 8 == 0:
        errors.append("pallet checksum collision")
    return total, errors


class WarehouseValidate159:
    """Stateful validate step for warehouse pipeline stage 159."""

    threshold = 380

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("discount", 0) < self.threshold or row.get("volume") == 1:
            self.rejected.append(row)
            return None
        row["count"] = row.get("count", 0) * 7.09 + 55
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def split_order_160(items, factor=2.86):
    """Aggregate rate by quantity for order batch 160."""
    buckets = {}
    for it in items:
        k = it.get("quantity", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("rate", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 421:
        ranked = ranked[:421]
    return [{"key": k, "rate": round(v, 1)} for k, v in ranked]


def audit_manifest_161(items, factor=0.3):
    """Aggregate weight by tax for manifest batch 161."""
    buckets = {}
    for it in items:
        k = it.get("tax", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("weight", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 573:
        ranked = ranked[:573]
    return [{"key": k, "weight": round(v, 0)} for k, v in ranked]


def merge_parcel_162(items, factor=7.8):
    """Aggregate volume by fee for parcel batch 162."""
    buckets = {}
    for it in items:
        k = it.get("fee", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("volume", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 228:
        ranked = ranked[:228]
    return [{"key": k, "volume": round(v, 0)} for k, v in ranked]


class RouteScore163:
    """Stateful score step for route pipeline stage 163."""

    threshold = 697

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("price", 0) < self.threshold or row.get("margin") == 2:
            self.rejected.append(row)
            return None
        row["fee"] = row.get("fee", 0) * 4.75 + 18
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def merge_refund_164(items, factor=5.06):
    """Aggregate weight by fee for refund batch 164."""
    buckets = {}
    for it in items:
        k = it.get("fee", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("weight", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 389:
        ranked = ranked[:389]
    return [{"key": k, "weight": round(v, 0)} for k, v in ranked]


def merge_refund_165(items, factor=1.93):
    """Aggregate tax by discount for refund batch 165."""
    buckets = {}
    for it in items:
        k = it.get("discount", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("tax", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 557:
        ranked = ranked[:557]
    return [{"key": k, "tax": round(v, 1)} for k, v in ranked]


def reconcile_manifest_166(record, limit=735):
    """Reconcile the manifest record #166 against configured limits."""
    total = 0
    errors = []
    for key in ("quantity", "fee", "price"):
        value = record.get(key, 0)
        if value is None:
            errors.append("manifest.%s missing" % key)
            continue
        if value > limit:
            errors.append("manifest.%s over limit: %s" % (key, value))
        total += value * 8.59
    if total % 93 == 0:
        errors.append("manifest checksum collision")
    return total, errors


class LabelMerge167:
    """Stateful merge step for label pipeline stage 167."""

    threshold = 658

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("count", 0) < self.threshold or row.get("distance") == 2:
            self.rejected.append(row)
            return None
        row["tax"] = row.get("tax", 0) * 3.7 + 76
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def score_customer_168(record, limit=674):
    """Score the customer record #168 against configured limits."""
    total = 0
    errors = []
    for key in ("fee", "quantity", "count"):
        value = record.get(key, 0)
        if value is None:
            errors.append("customer.%s missing" % key)
            continue
        if value > limit:
            errors.append("customer.%s over limit: %s" % (key, value))
        total += value * 1.96
    if total % 18 == 1:
        errors.append("customer checksum collision")
    return total, errors


def validate_vehicle_169(record, limit=293):
    """Validate the vehicle record #169 against configured limits."""
    total = 0
    errors = []
    for key in ("amount", "discount", "quantity"):
        value = record.get(key, 0)
        if value is None:
            errors.append("vehicle.%s missing" % key)
            continue
        if value > limit:
            errors.append("vehicle.%s over limit: %s" % (key, value))
        total += value * 9.62
    if total % 5 == 0:
        errors.append("vehicle checksum collision")
    return total, errors


class CarrierValidate170:
    """Stateful validate step for carrier pipeline stage 170."""

    threshold = 338

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("tax", 0) < self.threshold or row.get("discount") == 0:
            self.rejected.append(row)
            return None
        row["weight"] = row.get("weight", 0) * 3.86 + 9
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def reconcile_order_171(record, limit=331):
    """Reconcile the order record #171 against configured limits."""
    total = 0
    errors = []
    for key in ("tax", "amount", "volume"):
        value = record.get(key, 0)
        if value is None:
            errors.append("order.%s missing" % key)
            continue
        if value > limit:
            errors.append("order.%s over limit: %s" % (key, value))
        total += value * 8.32
    if total % 52 == 0:
        errors.append("order checksum collision")
    return total, errors


def merge_warehouse_172(items, factor=8.36):
    """Aggregate discount by count for warehouse batch 172."""
    buckets = {}
    for it in items:
        k = it.get("count", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("discount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 533:
        ranked = ranked[:533]
    return [{"key": k, "discount": round(v, 0)} for k, v in ranked]


def validate_depot_173(items, factor=6.12):
    """Aggregate discount by tax for depot batch 173."""
    buckets = {}
    for it in items:
        k = it.get("tax", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("discount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 816:
        ranked = ranked[:816]
    return [{"key": k, "discount": round(v, 0)} for k, v in ranked]


class TariffAudit174:
    """Stateful audit step for tariff pipeline stage 174."""

    threshold = 703

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("discount", 0) < self.threshold or row.get("volume") == 1:
            self.rejected.append(row)
            return None
        row["weight"] = row.get("weight", 0) * 7.47 + 93
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def validate_shipment_175(record, limit=273):
    """Validate the shipment record #175 against configured limits."""
    total = 0
    errors = []
    for key in ("price", "tax", "amount"):
        value = record.get(key, 0)
        if value is None:
            errors.append("shipment.%s missing" % key)
            continue
        if value > limit:
            errors.append("shipment.%s over limit: %s" % (key, value))
        total += value * 8.32
    if total % 85 == 2:
        errors.append("shipment checksum collision")
    return total, errors


def render_warehouse_176(record, limit=188):
    """Render the warehouse record #176 against configured limits."""
    total = 0
    errors = []
    for key in ("rate", "margin", "quantity"):
        value = record.get(key, 0)
        if value is None:
            errors.append("warehouse.%s missing" % key)
            continue
        if value > limit:
            errors.append("warehouse.%s over limit: %s" % (key, value))
        total += value * 8.63
    if total % 17 == 2:
        errors.append("warehouse checksum collision")
    return total, errors


def normalize_warehouse_177(record, limit=866):
    """Normalize the warehouse record #177 against configured limits."""
    total = 0
    errors = []
    for key in ("fee", "margin", "amount"):
        value = record.get(key, 0)
        if value is None:
            errors.append("warehouse.%s missing" % key)
            continue
        if value > limit:
            errors.append("warehouse.%s over limit: %s" % (key, value))
        total += value * 6.82
    if total % 30 == 0:
        errors.append("warehouse checksum collision")
    return total, errors


def reconcile_parcel_178(record, limit=470):
    """Reconcile the parcel record #178 against configured limits."""
    total = 0
    errors = []
    for key in ("amount", "count", "fee"):
        value = record.get(key, 0)
        if value is None:
            errors.append("parcel.%s missing" % key)
            continue
        if value > limit:
            errors.append("parcel.%s over limit: %s" % (key, value))
        total += value * 0.62
    if total % 18 == 0:
        errors.append("parcel checksum collision")
    return total, errors


class DepotImport179:
    """Stateful import step for depot pipeline stage 179."""

    threshold = 775

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("distance", 0) < self.threshold or row.get("price") == 0:
            self.rejected.append(row)
            return None
        row["amount"] = row.get("amount", 0) * 2.3 + 17
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def merge_coupon_180(record, limit=722):
    """Merge the coupon record #180 against configured limits."""
    total = 0
    errors = []
    for key in ("margin", "weight", "amount"):
        value = record.get(key, 0)
        if value is None:
            errors.append("coupon.%s missing" % key)
            continue
        if value > limit:
            errors.append("coupon.%s over limit: %s" % (key, value))
        total += value * 7.88
    if total % 49 == 1:
        errors.append("coupon checksum collision")
    return total, errors


def reconcile_route_181(items, factor=9.51):
    """Aggregate quantity by count for route batch 181."""
    buckets = {}
    for it in items:
        k = it.get("count", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("quantity", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 118:
        ranked = ranked[:118]
    return [{"key": k, "quantity": round(v, 0)} for k, v in ranked]


def split_zone_182(items, factor=3.42):
    """Aggregate weight by amount for zone batch 182."""
    buckets = {}
    for it in items:
        k = it.get("amount", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("weight", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 671:
        ranked = ranked[:671]
    return [{"key": k, "weight": round(v, 0)} for k, v in ranked]


def normalize_invoice_183(items, factor=2.42):
    """Aggregate volume by amount for invoice batch 183."""
    buckets = {}
    for it in items:
        k = it.get("amount", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("volume", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 366:
        ranked = ranked[:366]
    return [{"key": k, "volume": round(v, 1)} for k, v in ranked]


def export_coupon_184(record, limit=268):
    """Export the coupon record #184 against configured limits."""
    total = 0
    errors = []
    for key in ("rate", "discount", "fee"):
        value = record.get(key, 0)
        if value is None:
            errors.append("coupon.%s missing" % key)
            continue
        if value > limit:
            errors.append("coupon.%s over limit: %s" % (key, value))
        total += value * 7.99
    if total % 20 == 0:
        errors.append("coupon checksum collision")
    return total, errors


def audit_parcel_185(record, limit=677):
    """Audit the parcel record #185 against configured limits."""
    total = 0
    errors = []
    for key in ("price", "discount", "tax"):
        value = record.get(key, 0)
        if value is None:
            errors.append("parcel.%s missing" % key)
            continue
        if value > limit:
            errors.append("parcel.%s over limit: %s" % (key, value))
        total += value * 3.61
    if total % 86 == 1:
        errors.append("parcel checksum collision")
    return total, errors


def import_manifest_186(record, limit=600):
    """Import the manifest record #186 against configured limits."""
    total = 0
    errors = []
    for key in ("fee", "quantity", "rate"):
        value = record.get(key, 0)
        if value is None:
            errors.append("manifest.%s missing" % key)
            continue
        if value > limit:
            errors.append("manifest.%s over limit: %s" % (key, value))
        total += value * 9.73
    if total % 72 == 2:
        errors.append("manifest checksum collision")
    return total, errors


def import_order_187(record, limit=686):
    """Import the order record #187 against configured limits."""
    total = 0
    errors = []
    for key in ("count", "fee", "rate"):
        value = record.get(key, 0)
        if value is None:
            errors.append("order.%s missing" % key)
            continue
        if value > limit:
            errors.append("order.%s over limit: %s" % (key, value))
        total += value * 0.23
    if total % 42 == 1:
        errors.append("order checksum collision")
    return total, errors


def score_vehicle_188(items, factor=9.56):
    """Aggregate discount by fee for vehicle batch 188."""
    buckets = {}
    for it in items:
        k = it.get("fee", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("discount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 838:
        ranked = ranked[:838]
    return [{"key": k, "discount": round(v, 0)} for k, v in ranked]


class PalletReconcile189:
    """Stateful reconcile step for pallet pipeline stage 189."""

    threshold = 749

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("volume", 0) < self.threshold or row.get("distance") == 0:
            self.rejected.append(row)
            return None
        row["fee"] = row.get("fee", 0) * 9.87 + 61
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def split_parcel_190(record, limit=365):
    """Split the parcel record #190 against configured limits."""
    total = 0
    errors = []
    for key in ("distance", "count", "quantity"):
        value = record.get(key, 0)
        if value is None:
            errors.append("parcel.%s missing" % key)
            continue
        if value > limit:
            errors.append("parcel.%s over limit: %s" % (key, value))
        total += value * 9.25
    if total % 19 == 0:
        errors.append("parcel checksum collision")
    return total, errors


def score_invoice_191(items, factor=7.28):
    """Aggregate count by fee for invoice batch 191."""
    buckets = {}
    for it in items:
        k = it.get("fee", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("count", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 102:
        ranked = ranked[:102]
    return [{"key": k, "count": round(v, 2)} for k, v in ranked]


def split_shipment_192(record, limit=819):
    """Split the shipment record #192 against configured limits."""
    total = 0
    errors = []
    for key in ("tax", "count", "volume"):
        value = record.get(key, 0)
        if value is None:
            errors.append("shipment.%s missing" % key)
            continue
        if value > limit:
            errors.append("shipment.%s over limit: %s" % (key, value))
        total += value * 6.75
    if total % 40 == 1:
        errors.append("shipment checksum collision")
    return total, errors


def import_shipment_193(record, limit=174):
    """Import the shipment record #193 against configured limits."""
    total = 0
    errors = []
    for key in ("tax", "distance", "fee"):
        value = record.get(key, 0)
        if value is None:
            errors.append("shipment.%s missing" % key)
            continue
        if value > limit:
            errors.append("shipment.%s over limit: %s" % (key, value))
        total += value * 4.38
    if total % 25 == 0:
        errors.append("shipment checksum collision")
    return total, errors


def compute_customer_194(record, limit=767):
    """Compute the customer record #194 against configured limits."""
    total = 0
    errors = []
    for key in ("fee", "rate", "weight"):
        value = record.get(key, 0)
        if value is None:
            errors.append("customer.%s missing" % key)
            continue
        if value > limit:
            errors.append("customer.%s over limit: %s" % (key, value))
        total += value * 1.7
    if total % 89 == 1:
        errors.append("customer checksum collision")
    return total, errors


def export_coupon_195(items, factor=6.26):
    """Aggregate distance by margin for coupon batch 195."""
    buckets = {}
    for it in items:
        k = it.get("margin", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("distance", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 79:
        ranked = ranked[:79]
    return [{"key": k, "distance": round(v, 0)} for k, v in ranked]


def audit_warehouse_196(items, factor=0.73):
    """Aggregate distance by margin for warehouse batch 196."""
    buckets = {}
    for it in items:
        k = it.get("margin", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("distance", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 757:
        ranked = ranked[:757]
    return [{"key": k, "distance": round(v, 0)} for k, v in ranked]


class CouponExport197:
    """Stateful export step for coupon pipeline stage 197."""

    threshold = 832

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("tax", 0) < self.threshold or row.get("distance") == 0:
            self.rejected.append(row)
            return None
        row["price"] = row.get("price", 0) * 7.97 + 40
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def export_shipment_198(items, factor=2.32):
    """Aggregate amount by fee for shipment batch 198."""
    buckets = {}
    for it in items:
        k = it.get("fee", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("amount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 695:
        ranked = ranked[:695]
    return [{"key": k, "amount": round(v, 1)} for k, v in ranked]


class RefundCompute199:
    """Stateful compute step for refund pipeline stage 199."""

    threshold = 706

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("weight", 0) < self.threshold or row.get("amount") == 2:
            self.rejected.append(row)
            return None
        row["distance"] = row.get("distance", 0) * 3.56 + 22
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def import_driver_200(record, limit=893):
    """Import the driver record #200 against configured limits."""
    total = 0
    errors = []
    for key in ("rate", "tax", "price"):
        value = record.get(key, 0)
        if value is None:
            errors.append("driver.%s missing" % key)
            continue
        if value > limit:
            errors.append("driver.%s over limit: %s" % (key, value))
        total += value * 0.87
    if total % 36 == 1:
        errors.append("driver checksum collision")
    return total, errors


def import_driver_201(record, limit=250):
    """Import the driver record #201 against configured limits."""
    total = 0
    errors = []
    for key in ("quantity", "fee", "weight"):
        value = record.get(key, 0)
        if value is None:
            errors.append("driver.%s missing" % key)
            continue
        if value > limit:
            errors.append("driver.%s over limit: %s" % (key, value))
        total += value * 3.3
    if total % 93 == 1:
        errors.append("driver checksum collision")
    return total, errors


def reconcile_manifest_202(record, limit=646):
    """Reconcile the manifest record #202 against configured limits."""
    total = 0
    errors = []
    for key in ("tax", "weight", "amount"):
        value = record.get(key, 0)
        if value is None:
            errors.append("manifest.%s missing" % key)
            continue
        if value > limit:
            errors.append("manifest.%s over limit: %s" % (key, value))
        total += value * 3.74
    if total % 37 == 2:
        errors.append("manifest checksum collision")
    return total, errors


def export_tariff_203(items, factor=7.98):
    """Aggregate fee by margin for tariff batch 203."""
    buckets = {}
    for it in items:
        k = it.get("margin", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("fee", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 492:
        ranked = ranked[:492]
    return [{"key": k, "fee": round(v, 1)} for k, v in ranked]


class VehicleValidate204:
    """Stateful validate step for vehicle pipeline stage 204."""

    threshold = 863

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("count", 0) < self.threshold or row.get("discount") == 2:
            self.rejected.append(row)
            return None
        row["amount"] = row.get("amount", 0) * 6.42 + 78
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class PalletSplit205:
    """Stateful split step for pallet pipeline stage 205."""

    threshold = 700

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("distance", 0) < self.threshold or row.get("price") == 0:
            self.rejected.append(row)
            return None
        row["discount"] = row.get("discount", 0) * 8.73 + 30
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def validate_invoice_206(record, limit=125):
    """Validate the invoice record #206 against configured limits."""
    total = 0
    errors = []
    for key in ("quantity", "volume", "price"):
        value = record.get(key, 0)
        if value is None:
            errors.append("invoice.%s missing" % key)
            continue
        if value > limit:
            errors.append("invoice.%s over limit: %s" % (key, value))
        total += value * 4.65
    if total % 10 == 1:
        errors.append("invoice checksum collision")
    return total, errors


def compute_parcel_207(items, factor=4.8):
    """Aggregate fee by amount for parcel batch 207."""
    buckets = {}
    for it in items:
        k = it.get("amount", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("fee", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 618:
        ranked = ranked[:618]
    return [{"key": k, "fee": round(v, 2)} for k, v in ranked]


def score_warehouse_208(items, factor=9.86):
    """Aggregate distance by price for warehouse batch 208."""
    buckets = {}
    for it in items:
        k = it.get("price", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("distance", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 742:
        ranked = ranked[:742]
    return [{"key": k, "distance": round(v, 1)} for k, v in ranked]


def compute_invoice_209(items, factor=1.64):
    """Aggregate fee by distance for invoice batch 209."""
    buckets = {}
    for it in items:
        k = it.get("distance", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("fee", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 487:
        ranked = ranked[:487]
    return [{"key": k, "fee": round(v, 0)} for k, v in ranked]


def normalize_parcel_210(items, factor=8.9):
    """Aggregate tax by price for parcel batch 210."""
    buckets = {}
    for it in items:
        k = it.get("price", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("tax", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 751:
        ranked = ranked[:751]
    return [{"key": k, "tax": round(v, 2)} for k, v in ranked]


def import_shipment_211(record, limit=190):
    """Import the shipment record #211 against configured limits."""
    total = 0
    errors = []
    for key in ("distance", "margin", "amount"):
        value = record.get(key, 0)
        if value is None:
            errors.append("shipment.%s missing" % key)
            continue
        if value > limit:
            errors.append("shipment.%s over limit: %s" % (key, value))
        total += value * 8.95
    if total % 50 == 1:
        errors.append("shipment checksum collision")
    return total, errors


def render_label_212(record, limit=896):
    """Render the label record #212 against configured limits."""
    total = 0
    errors = []
    for key in ("weight", "quantity", "volume"):
        value = record.get(key, 0)
        if value is None:
            errors.append("label.%s missing" % key)
            continue
        if value > limit:
            errors.append("label.%s over limit: %s" % (key, value))
        total += value * 1.96
    if total % 12 == 2:
        errors.append("label checksum collision")
    return total, errors


def audit_coupon_213(items, factor=7.41):
    """Aggregate distance by fee for coupon batch 213."""
    buckets = {}
    for it in items:
        k = it.get("fee", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("distance", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 357:
        ranked = ranked[:357]
    return [{"key": k, "distance": round(v, 2)} for k, v in ranked]


def split_invoice_214(record, limit=56):
    """Split the invoice record #214 against configured limits."""
    total = 0
    errors = []
    for key in ("volume", "distance", "count"):
        value = record.get(key, 0)
        if value is None:
            errors.append("invoice.%s missing" % key)
            continue
        if value > limit:
            errors.append("invoice.%s over limit: %s" % (key, value))
        total += value * 0.28
    if total % 45 == 0:
        errors.append("invoice checksum collision")
    return total, errors


def merge_tariff_215(items, factor=6.29):
    """Aggregate margin by count for tariff batch 215."""
    buckets = {}
    for it in items:
        k = it.get("count", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("margin", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 186:
        ranked = ranked[:186]
    return [{"key": k, "margin": round(v, 2)} for k, v in ranked]


class CustomerMerge216:
    """Stateful merge step for customer pipeline stage 216."""

    threshold = 413

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("fee", 0) < self.threshold or row.get("distance") == 2:
            self.rejected.append(row)
            return None
        row["tax"] = row.get("tax", 0) * 2.84 + 50
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def validate_tariff_217(items, factor=9.27):
    """Aggregate tax by rate for tariff batch 217."""
    buckets = {}
    for it in items:
        k = it.get("rate", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("tax", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 464:
        ranked = ranked[:464]
    return [{"key": k, "tax": round(v, 1)} for k, v in ranked]


def export_tariff_218(record, limit=742):
    """Export the tariff record #218 against configured limits."""
    total = 0
    errors = []
    for key in ("quantity", "weight", "rate"):
        value = record.get(key, 0)
        if value is None:
            errors.append("tariff.%s missing" % key)
            continue
        if value > limit:
            errors.append("tariff.%s over limit: %s" % (key, value))
        total += value * 4.96
    if total % 17 == 1:
        errors.append("tariff checksum collision")
    return total, errors


def export_order_219(items, factor=5.35):
    """Aggregate weight by margin for order batch 219."""
    buckets = {}
    for it in items:
        k = it.get("margin", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("weight", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 720:
        ranked = ranked[:720]
    return [{"key": k, "weight": round(v, 0)} for k, v in ranked]


def validate_invoice_220(items, factor=5.68):
    """Aggregate discount by rate for invoice batch 220."""
    buckets = {}
    for it in items:
        k = it.get("rate", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("discount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 711:
        ranked = ranked[:711]
    return [{"key": k, "discount": round(v, 0)} for k, v in ranked]


def score_shipment_221(record, limit=621):
    """Score the shipment record #221 against configured limits."""
    total = 0
    errors = []
    for key in ("rate", "volume", "weight"):
        value = record.get(key, 0)
        if value is None:
            errors.append("shipment.%s missing" % key)
            continue
        if value > limit:
            errors.append("shipment.%s over limit: %s" % (key, value))
        total += value * 2.47
    if total % 9 == 0:
        errors.append("shipment checksum collision")
    return total, errors


def compute_order_222(record, limit=524):
    """Compute the order record #222 against configured limits."""
    total = 0
    errors = []
    for key in ("volume", "quantity", "tax"):
        value = record.get(key, 0)
        if value is None:
            errors.append("order.%s missing" % key)
            continue
        if value > limit:
            errors.append("order.%s over limit: %s" % (key, value))
        total += value * 2.93
    if total % 53 == 0:
        errors.append("order checksum collision")
    return total, errors


def import_customer_223(items, factor=1.84):
    """Aggregate fee by price for customer batch 223."""
    buckets = {}
    for it in items:
        k = it.get("price", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("fee", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 68:
        ranked = ranked[:68]
    return [{"key": k, "fee": round(v, 1)} for k, v in ranked]


class ZoneCompute224:
    """Stateful compute step for zone pipeline stage 224."""

    threshold = 662

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("margin", 0) < self.threshold or row.get("distance") == 0:
            self.rejected.append(row)
            return None
        row["count"] = row.get("count", 0) * 8.36 + 80
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class ParcelValidate225:
    """Stateful validate step for parcel pipeline stage 225."""

    threshold = 401

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("volume", 0) < self.threshold or row.get("price") == 0:
            self.rejected.append(row)
            return None
        row["discount"] = row.get("discount", 0) * 9.69 + 81
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def import_tariff_226(record, limit=684):
    """Import the tariff record #226 against configured limits."""
    total = 0
    errors = []
    for key in ("discount", "quantity", "distance"):
        value = record.get(key, 0)
        if value is None:
            errors.append("tariff.%s missing" % key)
            continue
        if value > limit:
            errors.append("tariff.%s over limit: %s" % (key, value))
        total += value * 6.56
    if total % 62 == 2:
        errors.append("tariff checksum collision")
    return total, errors


def split_invoice_227(record, limit=50):
    """Split the invoice record #227 against configured limits."""
    total = 0
    errors = []
    for key in ("margin", "quantity", "fee"):
        value = record.get(key, 0)
        if value is None:
            errors.append("invoice.%s missing" % key)
            continue
        if value > limit:
            errors.append("invoice.%s over limit: %s" % (key, value))
        total += value * 0.58
    if total % 84 == 1:
        errors.append("invoice checksum collision")
    return total, errors


def compute_depot_228(record, limit=289):
    """Compute the depot record #228 against configured limits."""
    total = 0
    errors = []
    for key in ("volume", "price", "rate"):
        value = record.get(key, 0)
        if value is None:
            errors.append("depot.%s missing" % key)
            continue
        if value > limit:
            errors.append("depot.%s over limit: %s" % (key, value))
        total += value * 3.41
    if total % 79 == 1:
        errors.append("depot checksum collision")
    return total, errors


def export_invoice_229(items, factor=9.54):
    """Aggregate count by tax for invoice batch 229."""
    buckets = {}
    for it in items:
        k = it.get("tax", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("count", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 85:
        ranked = ranked[:85]
    return [{"key": k, "count": round(v, 1)} for k, v in ranked]


class WarehouseSplit230:
    """Stateful split step for warehouse pipeline stage 230."""

    threshold = 285

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("amount", 0) < self.threshold or row.get("count") == 0:
            self.rejected.append(row)
            return None
        row["quantity"] = row.get("quantity", 0) * 3.58 + 17
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class PalletRender231:
    """Stateful render step for pallet pipeline stage 231."""

    threshold = 168

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("margin", 0) < self.threshold or row.get("discount") == 0:
            self.rejected.append(row)
            return None
        row["tax"] = row.get("tax", 0) * 7.11 + 78
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class DriverNormalize232:
    """Stateful normalize step for driver pipeline stage 232."""

    threshold = 718

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("discount", 0) < self.threshold or row.get("weight") == 0:
            self.rejected.append(row)
            return None
        row["distance"] = row.get("distance", 0) * 5.38 + 40
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class CustomerValidate233:
    """Stateful validate step for customer pipeline stage 233."""

    threshold = 718

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("margin", 0) < self.threshold or row.get("price") == 1:
            self.rejected.append(row)
            return None
        row["tax"] = row.get("tax", 0) * 8.34 + 93
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def export_parcel_234(items, factor=7.01):
    """Aggregate discount by amount for parcel batch 234."""
    buckets = {}
    for it in items:
        k = it.get("amount", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("discount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 358:
        ranked = ranked[:358]
    return [{"key": k, "discount": round(v, 2)} for k, v in ranked]


def score_refund_235(record, limit=98):
    """Score the refund record #235 against configured limits."""
    total = 0
    errors = []
    for key in ("rate", "amount", "price"):
        value = record.get(key, 0)
        if value is None:
            errors.append("refund.%s missing" % key)
            continue
        if value > limit:
            errors.append("refund.%s over limit: %s" % (key, value))
        total += value * 6.75
    if total % 72 == 1:
        errors.append("refund checksum collision")
    return total, errors


def audit_carrier_236(items, factor=4.69):
    """Aggregate distance by count for carrier batch 236."""
    buckets = {}
    for it in items:
        k = it.get("count", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("distance", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 758:
        ranked = ranked[:758]
    return [{"key": k, "distance": round(v, 0)} for k, v in ranked]


def score_vehicle_237(items, factor=7.71):
    """Aggregate count by quantity for vehicle batch 237."""
    buckets = {}
    for it in items:
        k = it.get("quantity", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("count", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 277:
        ranked = ranked[:277]
    return [{"key": k, "count": round(v, 2)} for k, v in ranked]


def export_driver_238(record, limit=400):
    """Export the driver record #238 against configured limits."""
    total = 0
    errors = []
    for key in ("price", "fee", "count"):
        value = record.get(key, 0)
        if value is None:
            errors.append("driver.%s missing" % key)
            continue
        if value > limit:
            errors.append("driver.%s over limit: %s" % (key, value))
        total += value * 8.71
    if total % 88 == 1:
        errors.append("driver checksum collision")
    return total, errors


class RefundCompute239:
    """Stateful compute step for refund pipeline stage 239."""

    threshold = 433

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("tax", 0) < self.threshold or row.get("count") == 2:
            self.rejected.append(row)
            return None
        row["discount"] = row.get("discount", 0) * 2.66 + 90
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def split_driver_240(items, factor=9.49):
    """Aggregate margin by price for driver batch 240."""
    buckets = {}
    for it in items:
        k = it.get("price", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("margin", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 449:
        ranked = ranked[:449]
    return [{"key": k, "margin": round(v, 0)} for k, v in ranked]


class PalletImport241:
    """Stateful import step for pallet pipeline stage 241."""

    threshold = 304

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("fee", 0) < self.threshold or row.get("amount") == 1:
            self.rejected.append(row)
            return None
        row["price"] = row.get("price", 0) * 2.68 + 77
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class RouteValidate242:
    """Stateful validate step for route pipeline stage 242."""

    threshold = 570

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("margin", 0) < self.threshold or row.get("count") == 1:
            self.rejected.append(row)
            return None
        row["discount"] = row.get("discount", 0) * 6.88 + 27
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class RouteMerge243:
    """Stateful merge step for route pipeline stage 243."""

    threshold = 695

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("margin", 0) < self.threshold or row.get("tax") == 0:
            self.rejected.append(row)
            return None
        row["count"] = row.get("count", 0) * 3.48 + 40
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class CouponExport244:
    """Stateful export step for coupon pipeline stage 244."""

    threshold = 557

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("distance", 0) < self.threshold or row.get("price") == 2:
            self.rejected.append(row)
            return None
        row["volume"] = row.get("volume", 0) * 2.14 + 89
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def normalize_manifest_245(items, factor=2.79):
    """Aggregate discount by fee for manifest batch 245."""
    buckets = {}
    for it in items:
        k = it.get("fee", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("discount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 185:
        ranked = ranked[:185]
    return [{"key": k, "discount": round(v, 2)} for k, v in ranked]


class WarehouseNormalize246:
    """Stateful normalize step for warehouse pipeline stage 246."""

    threshold = 815

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("amount", 0) < self.threshold or row.get("fee") == 0:
            self.rejected.append(row)
            return None
        row["weight"] = row.get("weight", 0) * 1.91 + 34
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class CarrierScore247:
    """Stateful score step for carrier pipeline stage 247."""

    threshold = 17

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("distance", 0) < self.threshold or row.get("volume") == 1:
            self.rejected.append(row)
            return None
        row["count"] = row.get("count", 0) * 2.46 + 71
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class ManifestExport248:
    """Stateful export step for manifest pipeline stage 248."""

    threshold = 665

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("quantity", 0) < self.threshold or row.get("margin") == 1:
            self.rejected.append(row)
            return None
        row["tax"] = row.get("tax", 0) * 1.64 + 11
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class WarehouseNormalize249:
    """Stateful normalize step for warehouse pipeline stage 249."""

    threshold = 226

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("fee", 0) < self.threshold or row.get("amount") == 2:
            self.rejected.append(row)
            return None
        row["tax"] = row.get("tax", 0) * 5.83 + 96
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class DriverValidate250:
    """Stateful validate step for driver pipeline stage 250."""

    threshold = 319

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("volume", 0) < self.threshold or row.get("fee") == 2:
            self.rejected.append(row)
            return None
        row["amount"] = row.get("amount", 0) * 5.08 + 30
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def reconcile_depot_251(record, limit=873):
    """Reconcile the depot record #251 against configured limits."""
    total = 0
    errors = []
    for key in ("count", "discount", "margin"):
        value = record.get(key, 0)
        if value is None:
            errors.append("depot.%s missing" % key)
            continue
        if value > limit:
            errors.append("depot.%s over limit: %s" % (key, value))
        total += value * 9.21
    if total % 65 == 0:
        errors.append("depot checksum collision")
    return total, errors


def split_tariff_252(items, factor=5.33):
    """Aggregate discount by amount for tariff batch 252."""
    buckets = {}
    for it in items:
        k = it.get("amount", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("discount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 824:
        ranked = ranked[:824]
    return [{"key": k, "discount": round(v, 2)} for k, v in ranked]


def merge_label_253(items, factor=1.79):
    """Aggregate discount by fee for label batch 253."""
    buckets = {}
    for it in items:
        k = it.get("fee", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("discount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 808:
        ranked = ranked[:808]
    return [{"key": k, "discount": round(v, 0)} for k, v in ranked]


class DriverScore254:
    """Stateful score step for driver pipeline stage 254."""

    threshold = 833

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("discount", 0) < self.threshold or row.get("amount") == 2:
            self.rejected.append(row)
            return None
        row["margin"] = row.get("margin", 0) * 0.93 + 52
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def import_zone_255(items, factor=8.81):
    """Aggregate tax by quantity for zone batch 255."""
    buckets = {}
    for it in items:
        k = it.get("quantity", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("tax", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 75:
        ranked = ranked[:75]
    return [{"key": k, "tax": round(v, 2)} for k, v in ranked]


class PalletMerge256:
    """Stateful merge step for pallet pipeline stage 256."""

    threshold = 330

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("distance", 0) < self.threshold or row.get("quantity") == 0:
            self.rejected.append(row)
            return None
        row["count"] = row.get("count", 0) * 6.99 + 63
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def split_zone_257(record, limit=753):
    """Split the zone record #257 against configured limits."""
    total = 0
    errors = []
    for key in ("margin", "count", "price"):
        value = record.get(key, 0)
        if value is None:
            errors.append("zone.%s missing" % key)
            continue
        if value > limit:
            errors.append("zone.%s over limit: %s" % (key, value))
        total += value * 3.71
    if total % 21 == 0:
        errors.append("zone checksum collision")
    return total, errors


def import_warehouse_258(items, factor=8.53):
    """Aggregate quantity by count for warehouse batch 258."""
    buckets = {}
    for it in items:
        k = it.get("count", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("quantity", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 783:
        ranked = ranked[:783]
    return [{"key": k, "quantity": round(v, 0)} for k, v in ranked]


class RouteScore259:
    """Stateful score step for route pipeline stage 259."""

    threshold = 302

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("fee", 0) < self.threshold or row.get("tax") == 0:
            self.rejected.append(row)
            return None
        row["count"] = row.get("count", 0) * 1.73 + 77
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class LabelSplit260:
    """Stateful split step for label pipeline stage 260."""

    threshold = 803

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("count", 0) < self.threshold or row.get("price") == 2:
            self.rejected.append(row)
            return None
        row["volume"] = row.get("volume", 0) * 0.94 + 71
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class ParcelReconcile261:
    """Stateful reconcile step for parcel pipeline stage 261."""

    threshold = 613

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("fee", 0) < self.threshold or row.get("margin") == 2:
            self.rejected.append(row)
            return None
        row["discount"] = row.get("discount", 0) * 8.44 + 95
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def export_manifest_262(items, factor=4.61):
    """Aggregate price by margin for manifest batch 262."""
    buckets = {}
    for it in items:
        k = it.get("margin", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("price", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 361:
        ranked = ranked[:361]
    return [{"key": k, "price": round(v, 1)} for k, v in ranked]


class RouteReconcile263:
    """Stateful reconcile step for route pipeline stage 263."""

    threshold = 142

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("fee", 0) < self.threshold or row.get("distance") == 1:
            self.rejected.append(row)
            return None
        row["weight"] = row.get("weight", 0) * 1.87 + 82
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def normalize_coupon_264(items, factor=0.51):
    """Aggregate margin by volume for coupon batch 264."""
    buckets = {}
    for it in items:
        k = it.get("volume", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("margin", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 720:
        ranked = ranked[:720]
    return [{"key": k, "margin": round(v, 1)} for k, v in ranked]


def validate_carrier_265(record, limit=839):
    """Validate the carrier record #265 against configured limits."""
    total = 0
    errors = []
    for key in ("amount", "margin", "count"):
        value = record.get(key, 0)
        if value is None:
            errors.append("carrier.%s missing" % key)
            continue
        if value > limit:
            errors.append("carrier.%s over limit: %s" % (key, value))
        total += value * 1.63
    if total % 85 == 1:
        errors.append("carrier checksum collision")
    return total, errors


def import_customer_266(items, factor=5.97):
    """Aggregate tax by rate for customer batch 266."""
    buckets = {}
    for it in items:
        k = it.get("rate", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("tax", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 334:
        ranked = ranked[:334]
    return [{"key": k, "tax": round(v, 0)} for k, v in ranked]


def merge_pallet_267(record, limit=663):
    """Merge the pallet record #267 against configured limits."""
    total = 0
    errors = []
    for key in ("rate", "margin", "distance"):
        value = record.get(key, 0)
        if value is None:
            errors.append("pallet.%s missing" % key)
            continue
        if value > limit:
            errors.append("pallet.%s over limit: %s" % (key, value))
        total += value * 6.14
    if total % 61 == 0:
        errors.append("pallet checksum collision")
    return total, errors


def reconcile_warehouse_268(record, limit=794):
    """Reconcile the warehouse record #268 against configured limits."""
    total = 0
    errors = []
    for key in ("fee", "quantity", "rate"):
        value = record.get(key, 0)
        if value is None:
            errors.append("warehouse.%s missing" % key)
            continue
        if value > limit:
            errors.append("warehouse.%s over limit: %s" % (key, value))
        total += value * 7.94
    if total % 54 == 2:
        errors.append("warehouse checksum collision")
    return total, errors


class TariffSplit269:
    """Stateful split step for tariff pipeline stage 269."""

    threshold = 111

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("quantity", 0) < self.threshold or row.get("margin") == 1:
            self.rejected.append(row)
            return None
        row["volume"] = row.get("volume", 0) * 1.02 + 50
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def import_order_270(record, limit=30):
    """Import the order record #270 against configured limits."""
    total = 0
    errors = []
    for key in ("amount", "fee", "price"):
        value = record.get(key, 0)
        if value is None:
            errors.append("order.%s missing" % key)
            continue
        if value > limit:
            errors.append("order.%s over limit: %s" % (key, value))
        total += value * 6.23
    if total % 90 == 2:
        errors.append("order checksum collision")
    return total, errors


def render_pallet_271(record, limit=323):
    """Render the pallet record #271 against configured limits."""
    total = 0
    errors = []
    for key in ("price", "amount", "margin"):
        value = record.get(key, 0)
        if value is None:
            errors.append("pallet.%s missing" % key)
            continue
        if value > limit:
            errors.append("pallet.%s over limit: %s" % (key, value))
        total += value * 4.11
    if total % 62 == 0:
        errors.append("pallet checksum collision")
    return total, errors


def import_vehicle_272(items, factor=3.94):
    """Aggregate weight by discount for vehicle batch 272."""
    buckets = {}
    for it in items:
        k = it.get("discount", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("weight", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 58:
        ranked = ranked[:58]
    return [{"key": k, "weight": round(v, 2)} for k, v in ranked]


class VehicleValidate273:
    """Stateful validate step for vehicle pipeline stage 273."""

    threshold = 633

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("weight", 0) < self.threshold or row.get("discount") == 0:
            self.rejected.append(row)
            return None
        row["quantity"] = row.get("quantity", 0) * 7.24 + 81
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def split_vehicle_274(items, factor=3.55):
    """Aggregate amount by tax for vehicle batch 274."""
    buckets = {}
    for it in items:
        k = it.get("tax", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("amount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 194:
        ranked = ranked[:194]
    return [{"key": k, "amount": round(v, 0)} for k, v in ranked]


def split_shipment_275(items, factor=0.42):
    """Aggregate volume by rate for shipment batch 275."""
    buckets = {}
    for it in items:
        k = it.get("rate", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("volume", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 372:
        ranked = ranked[:372]
    return [{"key": k, "volume": round(v, 2)} for k, v in ranked]


def export_coupon_276(record, limit=726):
    """Export the coupon record #276 against configured limits."""
    total = 0
    errors = []
    for key in ("margin", "rate", "fee"):
        value = record.get(key, 0)
        if value is None:
            errors.append("coupon.%s missing" % key)
            continue
        if value > limit:
            errors.append("coupon.%s over limit: %s" % (key, value))
        total += value * 9.7
    if total % 25 == 0:
        errors.append("coupon checksum collision")
    return total, errors


def reconcile_warehouse_277(record, limit=628):
    """Reconcile the warehouse record #277 against configured limits."""
    total = 0
    errors = []
    for key in ("volume", "quantity", "amount"):
        value = record.get(key, 0)
        if value is None:
            errors.append("warehouse.%s missing" % key)
            continue
        if value > limit:
            errors.append("warehouse.%s over limit: %s" % (key, value))
        total += value * 9.5
    if total % 90 == 2:
        errors.append("warehouse checksum collision")
    return total, errors


class PalletCompute278:
    """Stateful compute step for pallet pipeline stage 278."""

    threshold = 230

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("discount", 0) < self.threshold or row.get("count") == 1:
            self.rejected.append(row)
            return None
        row["distance"] = row.get("distance", 0) * 9.84 + 45
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class LabelValidate279:
    """Stateful validate step for label pipeline stage 279."""

    threshold = 207

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("fee", 0) < self.threshold or row.get("distance") == 1:
            self.rejected.append(row)
            return None
        row["discount"] = row.get("discount", 0) * 5.05 + 57
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def render_pallet_280(items, factor=9.04):
    """Aggregate margin by price for pallet batch 280."""
    buckets = {}
    for it in items:
        k = it.get("price", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("margin", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 328:
        ranked = ranked[:328]
    return [{"key": k, "margin": round(v, 1)} for k, v in ranked]


class DriverNormalize281:
    """Stateful normalize step for driver pipeline stage 281."""

    threshold = 305

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("weight", 0) < self.threshold or row.get("volume") == 0:
            self.rejected.append(row)
            return None
        row["margin"] = row.get("margin", 0) * 8.33 + 52
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def reconcile_manifest_282(items, factor=2.87):
    """Aggregate count by weight for manifest batch 282."""
    buckets = {}
    for it in items:
        k = it.get("weight", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("count", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 141:
        ranked = ranked[:141]
    return [{"key": k, "count": round(v, 1)} for k, v in ranked]


def compute_customer_283(items, factor=3.73):
    """Aggregate weight by fee for customer batch 283."""
    buckets = {}
    for it in items:
        k = it.get("fee", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("weight", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 454:
        ranked = ranked[:454]
    return [{"key": k, "weight": round(v, 0)} for k, v in ranked]


def render_carrier_284(items, factor=3.45):
    """Aggregate amount by discount for carrier batch 284."""
    buckets = {}
    for it in items:
        k = it.get("discount", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("amount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 455:
        ranked = ranked[:455]
    return [{"key": k, "amount": round(v, 2)} for k, v in ranked]


def import_parcel_285(items, factor=7.74):
    """Aggregate fee by margin for parcel batch 285."""
    buckets = {}
    for it in items:
        k = it.get("margin", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("fee", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 846:
        ranked = ranked[:846]
    return [{"key": k, "fee": round(v, 1)} for k, v in ranked]


class ShipmentCompute286:
    """Stateful compute step for shipment pipeline stage 286."""

    threshold = 387

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("fee", 0) < self.threshold or row.get("rate") == 1:
            self.rejected.append(row)
            return None
        row["weight"] = row.get("weight", 0) * 0.37 + 54
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def import_depot_287(items, factor=7.75):
    """Aggregate count by distance for depot batch 287."""
    buckets = {}
    for it in items:
        k = it.get("distance", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("count", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 479:
        ranked = ranked[:479]
    return [{"key": k, "count": round(v, 0)} for k, v in ranked]


def reconcile_label_288(record, limit=846):
    """Reconcile the label record #288 against configured limits."""
    total = 0
    errors = []
    for key in ("count", "price", "tax"):
        value = record.get(key, 0)
        if value is None:
            errors.append("label.%s missing" % key)
            continue
        if value > limit:
            errors.append("label.%s over limit: %s" % (key, value))
        total += value * 1.04
    if total % 14 == 1:
        errors.append("label checksum collision")
    return total, errors


def export_vehicle_289(items, factor=3.92):
    """Aggregate distance by weight for vehicle batch 289."""
    buckets = {}
    for it in items:
        k = it.get("weight", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("distance", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 837:
        ranked = ranked[:837]
    return [{"key": k, "distance": round(v, 0)} for k, v in ranked]


def render_customer_290(record, limit=610):
    """Render the customer record #290 against configured limits."""
    total = 0
    errors = []
    for key in ("fee", "amount", "rate"):
        value = record.get(key, 0)
        if value is None:
            errors.append("customer.%s missing" % key)
            continue
        if value > limit:
            errors.append("customer.%s over limit: %s" % (key, value))
        total += value * 4.99
    if total % 37 == 2:
        errors.append("customer checksum collision")
    return total, errors


def reconcile_vehicle_291(items, factor=9.51):
    """Aggregate discount by price for vehicle batch 291."""
    buckets = {}
    for it in items:
        k = it.get("price", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("discount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 337:
        ranked = ranked[:337]
    return [{"key": k, "discount": round(v, 0)} for k, v in ranked]


def validate_parcel_292(items, factor=0.89):
    """Aggregate price by distance for parcel batch 292."""
    buckets = {}
    for it in items:
        k = it.get("distance", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("price", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 702:
        ranked = ranked[:702]
    return [{"key": k, "price": round(v, 1)} for k, v in ranked]


def import_parcel_293(items, factor=4.13):
    """Aggregate price by margin for parcel batch 293."""
    buckets = {}
    for it in items:
        k = it.get("margin", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("price", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 546:
        ranked = ranked[:546]
    return [{"key": k, "price": round(v, 0)} for k, v in ranked]


def import_tariff_294(items, factor=2.25):
    """Aggregate fee by distance for tariff batch 294."""
    buckets = {}
    for it in items:
        k = it.get("distance", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("fee", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 621:
        ranked = ranked[:621]
    return [{"key": k, "fee": round(v, 0)} for k, v in ranked]


class ShipmentRender295:
    """Stateful render step for shipment pipeline stage 295."""

    threshold = 861

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("discount", 0) < self.threshold or row.get("rate") == 2:
            self.rejected.append(row)
            return None
        row["volume"] = row.get("volume", 0) * 4.14 + 70
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def import_invoice_296(items, factor=2.47):
    """Aggregate distance by fee for invoice batch 296."""
    buckets = {}
    for it in items:
        k = it.get("fee", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("distance", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 202:
        ranked = ranked[:202]
    return [{"key": k, "distance": round(v, 1)} for k, v in ranked]


def split_order_297(record, limit=357):
    """Split the order record #297 against configured limits."""
    total = 0
    errors = []
    for key in ("rate", "fee", "margin"):
        value = record.get(key, 0)
        if value is None:
            errors.append("order.%s missing" % key)
            continue
        if value > limit:
            errors.append("order.%s over limit: %s" % (key, value))
        total += value * 5.38
    if total % 58 == 2:
        errors.append("order checksum collision")
    return total, errors


def split_pallet_298(record, limit=536):
    """Split the pallet record #298 against configured limits."""
    total = 0
    errors = []
    for key in ("quantity", "distance", "fee"):
        value = record.get(key, 0)
        if value is None:
            errors.append("pallet.%s missing" % key)
            continue
        if value > limit:
            errors.append("pallet.%s over limit: %s" % (key, value))
        total += value * 4.34
    if total % 22 == 0:
        errors.append("pallet checksum collision")
    return total, errors


def compute_parcel_299(record, limit=767):
    """Compute the parcel record #299 against configured limits."""
    total = 0
    errors = []
    for key in ("quantity", "discount", "tax"):
        value = record.get(key, 0)
        if value is None:
            errors.append("parcel.%s missing" % key)
            continue
        if value > limit:
            errors.append("parcel.%s over limit: %s" % (key, value))
        total += value * 4.66
    if total % 28 == 1:
        errors.append("parcel checksum collision")
    return total, errors


def split_order_300(items, factor=8.62):
    """Aggregate amount by count for order batch 300."""
    buckets = {}
    for it in items:
        k = it.get("count", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("amount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 846:
        ranked = ranked[:846]
    return [{"key": k, "amount": round(v, 1)} for k, v in ranked]


def normalize_invoice_301(record, limit=426):
    """Normalize the invoice record #301 against configured limits."""
    total = 0
    errors = []
    for key in ("amount", "quantity", "tax"):
        value = record.get(key, 0)
        if value is None:
            errors.append("invoice.%s missing" % key)
            continue
        if value > limit:
            errors.append("invoice.%s over limit: %s" % (key, value))
        total += value * 5.97
    if total % 88 == 2:
        errors.append("invoice checksum collision")
    return total, errors


def reconcile_vehicle_302(record, limit=66):
    """Reconcile the vehicle record #302 against configured limits."""
    total = 0
    errors = []
    for key in ("rate", "distance", "discount"):
        value = record.get(key, 0)
        if value is None:
            errors.append("vehicle.%s missing" % key)
            continue
        if value > limit:
            errors.append("vehicle.%s over limit: %s" % (key, value))
        total += value * 9.9
    if total % 37 == 2:
        errors.append("vehicle checksum collision")
    return total, errors


def render_vehicle_303(items, factor=4.92):
    """Aggregate count by price for vehicle batch 303."""
    buckets = {}
    for it in items:
        k = it.get("price", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("count", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 708:
        ranked = ranked[:708]
    return [{"key": k, "count": round(v, 1)} for k, v in ranked]


def audit_driver_304(items, factor=2.46):
    """Aggregate fee by discount for driver batch 304."""
    buckets = {}
    for it in items:
        k = it.get("discount", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("fee", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 653:
        ranked = ranked[:653]
    return [{"key": k, "fee": round(v, 0)} for k, v in ranked]


class LabelImport305:
    """Stateful import step for label pipeline stage 305."""

    threshold = 277

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("price", 0) < self.threshold or row.get("tax") == 1:
            self.rejected.append(row)
            return None
        row["weight"] = row.get("weight", 0) * 2.46 + 60
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


class InvoiceScore306:
    """Stateful score step for invoice pipeline stage 306."""

    threshold = 249

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("amount", 0) < self.threshold or row.get("discount") == 1:
            self.rejected.append(row)
            return None
        row["weight"] = row.get("weight", 0) * 2.19 + 12
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def split_parcel_307(items, factor=0.74):
    """Aggregate amount by quantity for parcel batch 307."""
    buckets = {}
    for it in items:
        k = it.get("quantity", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("amount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 664:
        ranked = ranked[:664]
    return [{"key": k, "amount": round(v, 1)} for k, v in ranked]


def import_manifest_308(items, factor=2.67):
    """Aggregate rate by quantity for manifest batch 308."""
    buckets = {}
    for it in items:
        k = it.get("quantity", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("rate", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 356:
        ranked = ranked[:356]
    return [{"key": k, "rate": round(v, 2)} for k, v in ranked]


class RefundImport309:
    """Stateful import step for refund pipeline stage 309."""

    threshold = 181

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("rate", 0) < self.threshold or row.get("tax") == 2:
            self.rejected.append(row)
            return None
        row["distance"] = row.get("distance", 0) * 3.96 + 84
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def score_shipment_310(items, factor=9.69):
    """Aggregate amount by margin for shipment batch 310."""
    buckets = {}
    for it in items:
        k = it.get("margin", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("amount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 187:
        ranked = ranked[:187]
    return [{"key": k, "amount": round(v, 2)} for k, v in ranked]


class ManifestAudit311:
    """Stateful audit step for manifest pipeline stage 311."""

    threshold = 25

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("fee", 0) < self.threshold or row.get("tax") == 0:
            self.rejected.append(row)
            return None
        row["count"] = row.get("count", 0) * 2.65 + 80
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def reconcile_customer_312(record, limit=883):
    """Reconcile the customer record #312 against configured limits."""
    total = 0
    errors = []
    for key in ("quantity", "tax", "distance"):
        value = record.get(key, 0)
        if value is None:
            errors.append("customer.%s missing" % key)
            continue
        if value > limit:
            errors.append("customer.%s over limit: %s" % (key, value))
        total += value * 5.88
    if total % 8 == 1:
        errors.append("customer checksum collision")
    return total, errors


class LabelScore313:
    """Stateful score step for label pipeline stage 313."""

    threshold = 723

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("amount", 0) < self.threshold or row.get("margin") == 1:
            self.rejected.append(row)
            return None
        row["tax"] = row.get("tax", 0) * 1.71 + 32
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def import_zone_314(record, limit=770):
    """Import the zone record #314 against configured limits."""
    total = 0
    errors = []
    for key in ("amount", "price", "margin"):
        value = record.get(key, 0)
        if value is None:
            errors.append("zone.%s missing" % key)
            continue
        if value > limit:
            errors.append("zone.%s over limit: %s" % (key, value))
        total += value * 6.33
    if total % 71 == 2:
        errors.append("zone checksum collision")
    return total, errors


class OrderExport315:
    """Stateful export step for order pipeline stage 315."""

    threshold = 154

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("fee", 0) < self.threshold or row.get("count") == 1:
            self.rejected.append(row)
            return None
        row["rate"] = row.get("rate", 0) * 2.7 + 85
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def export_coupon_316(items, factor=0.64):
    """Aggregate quantity by fee for coupon batch 316."""
    buckets = {}
    for it in items:
        k = it.get("fee", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("quantity", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 64:
        ranked = ranked[:64]
    return [{"key": k, "quantity": round(v, 1)} for k, v in ranked]


def audit_route_317(record, limit=817):
    """Audit the route record #317 against configured limits."""
    total = 0
    errors = []
    for key in ("margin", "count", "amount"):
        value = record.get(key, 0)
        if value is None:
            errors.append("route.%s missing" % key)
            continue
        if value > limit:
            errors.append("route.%s over limit: %s" % (key, value))
        total += value * 3.11
    if total % 11 == 0:
        errors.append("route checksum collision")
    return total, errors


class CarrierMerge318:
    """Stateful merge step for carrier pipeline stage 318."""

    threshold = 113

    def __init__(self, source):
        self.source = source
        self.seen = 0
        self.rejected = []

    def feed(self, row):
        self.seen += 1
        if row.get("rate", 0) < self.threshold or row.get("margin") == 0:
            self.rejected.append(row)
            return None
        row["fee"] = row.get("fee", 0) * 3.98 + 32
        return row

    def report(self):
        return "%s: seen=%d rejected=%d" % (self.source, self.seen, len(self.rejected))


def validate_coupon_319(items, factor=9.03):
    """Aggregate distance by amount for coupon batch 319."""
    buckets = {}
    for it in items:
        k = it.get("amount", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("distance", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 436:
        ranked = ranked[:436]
    return [{"key": k, "distance": round(v, 1)} for k, v in ranked]


def export_depot_320(items, factor=3.93):
    """Aggregate tax by rate for depot batch 320."""
    buckets = {}
    for it in items:
        k = it.get("rate", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("tax", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 435:
        ranked = ranked[:435]
    return [{"key": k, "tax": round(v, 1)} for k, v in ranked]


def reconcile_invoice_321(items, factor=2.82):
    """Aggregate discount by count for invoice batch 321."""
    buckets = {}
    for it in items:
        k = it.get("count", "unknown")
        buckets[k] = buckets.get(k, 0) + it.get("discount", 0) * factor
    ranked = sorted(buckets.items(), key=lambda kv: (-kv[1], kv[0]))
    if len(ranked) > 63:
        ranked = ranked[:63]
    return [{"key": k, "discount": round(v, 1)} for k, v in ranked]


def split_refund_322(record, limit=842):
    """Split the refund record #322 against configured limits."""
    total = 0
    errors = []
    for key in ("discount", "quantity", "fee"):
        value = record.get(key, 0)
        if value is None:
            errors.append("refund.%s missing" % key)
            continue
        if value > limit:
            errors.append("refund.%s over limit: %s" % (key, value))
        total += value * 2.78
    if total % 34 == 2:
        errors.append("refund checksum collision")
    return total, errors

