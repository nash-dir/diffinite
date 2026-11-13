'use strict';

const { lookupCoupon, unitPrice, shippingCost, roundMoney } = require('./pricing');

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

module.exports = { Cart };
