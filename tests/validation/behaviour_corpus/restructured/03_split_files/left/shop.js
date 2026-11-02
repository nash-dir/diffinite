'use strict';

const CURRENCY_DIGITS = { USD: 2, EUR: 2, JPY: 0, KRW: 0 };

class Cart {
  constructor(currency) {
    this.currency = currency || 'USD';
    this.lines = new Map();
    this.coupons = [];
  }

  add(product, qty) {
    if (!product || !product.sku) {
      throw new TypeError('product with sku required');
    }
    const n = Number.isInteger(qty) && qty > 0 ? qty : 1;
    const existing = this.lines.get(product.sku);
    if (existing) {
      existing.qty += n;
    } else {
      this.lines.set(product.sku, { product, qty: n });
    }
    return this;
  }

  remove(sku, qty) {
    const line = this.lines.get(sku);
    if (!line) {
      return false;
    }
    if (qty === undefined || qty >= line.qty) {
      this.lines.delete(sku);
    } else {
      line.qty -= qty;
    }
    return true;
  }

  applyCoupon(code) {
    const coupon = lookupCoupon(code);
    if (!coupon) {
      throw new Error('invalid coupon: ' + code);
    }
    if (this.coupons.some((c) => c.code === coupon.code)) {
      return false;
    }
    if (!coupon.stackable && this.coupons.length > 0) {
      throw new Error('coupon cannot be combined: ' + code);
    }
    this.coupons.push(coupon);
    return true;
  }

  itemCount() {
    let total = 0;
    for (const line of this.lines.values()) {
      total += line.qty;
    }
    return total;
  }

  subtotal() {
    let sum = 0;
    for (const { product, qty } of this.lines.values()) {
      sum += unitPrice(product, qty) * qty;
    }
    return roundMoney(sum, this.currency);
  }

  discount() {
    const base = this.subtotal();
    let off = 0;
    for (const c of this.coupons) {
      if (c.type === 'percent') {
        off += (base - off) * (c.value / 100);
      } else if (c.type === 'fixed') {
        off += c.value;
      }
    }
    return roundMoney(Math.min(off, base), this.currency);
  }

  total(shippingRegion) {
    const net = this.subtotal() - this.discount();
    const ship = shippingCost(net, this.itemCount(), shippingRegion);
    return roundMoney(net + ship, this.currency);
  }
}

const COUPONS = {
  WELCOME10: { code: 'WELCOME10', type: 'percent', value: 10, stackable: false },
  FREESHIP: { code: 'FREESHIP', type: 'shipping', value: 0, stackable: true },
  TAKE5: { code: 'TAKE5', type: 'fixed', value: 5, stackable: true },
};

function lookupCoupon(code) {
  if (typeof code !== 'string') {
    return null;
  }
  return COUPONS[code.trim().toUpperCase()] || null;
}

function unitPrice(product, qty) {
  const tiers = product.tiers || [];
  let price = product.price;
  for (const tier of tiers) {
    if (qty >= tier.minQty && tier.price < price) {
      price = tier.price;
    }
  }
  return price;
}

function shippingCost(net, items, region) {
  if (net >= 100) {
    return 0;
  }
  const base = region === 'intl' ? 25 : 6;
  const perItem = region === 'intl' ? 3 : 0.5;
  return base + perItem * Math.max(0, items - 1);
}

function roundMoney(value, currency) {
  const digits = CURRENCY_DIGITS[currency] !== undefined ? CURRENCY_DIGITS[currency] : 2;
  const factor = Math.pow(10, digits);
  return Math.round(value * factor) / factor;
}

function formatMoney(value, currency) {
  const digits = CURRENCY_DIGITS[currency] !== undefined ? CURRENCY_DIGITS[currency] : 2;
  const fixed = value.toFixed(digits);
  const [whole, frac] = fixed.split('.');
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return currency + ' ' + (frac ? grouped + '.' + frac : grouped);
}

function receiptLines(cart, region) {
  const out = [];
  for (const { product, qty } of cart.lines.values()) {
    const price = unitPrice(product, qty);
    out.push(product.name.padEnd(24) + String(qty).padStart(4) + '  ' + formatMoney(price * qty, cart.currency));
  }
  out.push('-'.repeat(44));
  out.push('Subtotal'.padEnd(30) + formatMoney(cart.subtotal(), cart.currency));
  out.push('Discount'.padEnd(30) + formatMoney(cart.discount(), cart.currency));
  out.push('Total'.padEnd(30) + formatMoney(cart.total(region), cart.currency));
  return out;
}

module.exports = { Cart, lookupCoupon, unitPrice, shippingCost, roundMoney, formatMoney, receiptLines };
