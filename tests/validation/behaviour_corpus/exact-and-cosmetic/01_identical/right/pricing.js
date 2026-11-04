'use strict';

const TAX_RATES = {
  KR: 0.1,
  JP: 0.1,
  US_CA: 0.0725,
  DE: 0.19,
};

function roundCurrency(value, decimals = 2) {
  const factor = Math.pow(10, decimals);
  return Math.round((value + Number.EPSILON) * factor) / factor;
}

function lineTotal(line) {
  if (line.quantity <= 0) {
    throw new RangeError(`invalid quantity for ${line.sku}`);
  }
  const gross = line.unitPrice * line.quantity;
  const discount = line.discountPct ? gross * (line.discountPct / 100) : 0;
  return roundCurrency(gross - discount);
}

function applyCoupon(subtotal, coupon) {
  if (!coupon) return subtotal;
  if (coupon.expires && new Date(coupon.expires) < new Date()) {
    return subtotal;
  }
  if (coupon.type === 'percent') {
    return roundCurrency(subtotal * (1 - coupon.amount / 100));
  }
  if (coupon.type === 'fixed') {
    return Math.max(0, roundCurrency(subtotal - coupon.amount));
  }
  throw new Error(`unknown coupon type: ${coupon.type}`);
}

function shippingFor(weightKg, region) {
  const base = region === 'domestic' ? 3000 : 12000;
  const perKg = region === 'domestic' ? 500 : 2500;
  const billable = Math.ceil(Math.max(weightKg, 0.5));
  return base + perKg * (billable - 1);
}

function quote(cart, options = {}) {
  const lines = cart.lines.map((l) => ({ ...l, total: lineTotal(l) }));
  const subtotal = lines.reduce((acc, l) => acc + l.total, 0);
  const afterCoupon = applyCoupon(subtotal, options.coupon);
  const rate = TAX_RATES[options.taxRegion] ?? 0;
  const tax = roundCurrency(afterCoupon * rate);
  const weight = cart.lines.reduce((acc, l) => acc + (l.weightKg || 0) * l.quantity, 0);
  const shipping = options.pickup ? 0 : shippingFor(weight, options.region || 'domestic');
  return {
    lines,
    subtotal: roundCurrency(subtotal),
    discount: roundCurrency(subtotal - afterCoupon),
    tax,
    shipping,
    total: roundCurrency(afterCoupon + tax + shipping),
  };
}

module.exports = { quote, lineTotal, applyCoupon, shippingFor, roundCurrency };
