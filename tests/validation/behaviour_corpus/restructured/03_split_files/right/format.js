'use strict';

const { CURRENCY_DIGITS, unitPrice } = require('./pricing');

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

module.exports = { formatMoney, receiptLines };
