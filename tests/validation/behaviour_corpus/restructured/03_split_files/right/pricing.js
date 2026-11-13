'use strict';

const CURRENCY_DIGITS = { USD: 2, EUR: 2, JPY: 0, KRW: 0 };

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

module.exports = { CURRENCY_DIGITS, lookupCoupon, unitPrice, shippingCost, roundMoney };
