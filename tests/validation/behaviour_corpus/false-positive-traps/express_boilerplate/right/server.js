'use strict';

const express = require('express');
const helmet = require('helmet');
const cors = require('cors');
const morgan = require('morgan');
const { body, validationResult } = require('express-validator');

const app = express();
const PORT = process.env.PORT || 8080;

app.use(helmet());
app.use(cors({ origin: process.env.ALLOWED_ORIGIN || '*' }));
app.use(express.json({ limit: '100kb' }));
app.use(morgan('combined'));

const inventory = [
  { sku: 'A-100', name: 'Widget', qty: 12, price: 4.5 },
  { sku: 'B-220', name: 'Gadget', qty: 0, price: 19.99 },
];

function findItem(sku) {
  return inventory.find((it) => it.sku === sku);
}

function totalValue() {
  return inventory.reduce((sum, it) => sum + it.qty * it.price, 0);
}

app.get('/healthz', (req, res) => {
  res.json({ status: 'ok', items: inventory.length });
});

app.get('/items', (req, res) => {
  const inStock = req.query.inStock === 'true';
  const list = inStock ? inventory.filter((it) => it.qty > 0) : inventory;
  res.json(list);
});

app.get('/items/:sku', (req, res) => {
  const item = findItem(req.params.sku);
  if (!item) return res.status(404).json({ error: 'not found' });
  res.json(item);
});

app.post(
  '/items',
  body('sku').isString().notEmpty(),
  body('qty').isInt({ min: 0 }),
  body('price').isFloat({ min: 0 }),
  (req, res) => {
    const errors = validationResult(req);
    if (!errors.isEmpty()) {
      return res.status(422).json({ errors: errors.array() });
    }
    if (findItem(req.body.sku)) {
      return res.status(409).json({ error: 'duplicate sku' });
    }
    inventory.push({
      sku: req.body.sku,
      name: req.body.name || req.body.sku,
      qty: Number(req.body.qty),
      price: Number(req.body.price),
    });
    res.status(201).json({ ok: true });
  }
);

app.patch('/items/:sku/stock', (req, res) => {
  const item = findItem(req.params.sku);
  if (!item) return res.status(404).json({ error: 'not found' });
  const delta = parseInt(req.body.delta, 10);
  if (Number.isNaN(delta) || item.qty + delta < 0) {
    return res.status(400).json({ error: 'bad delta' });
  }
  item.qty += delta;
  res.json(item);
});

app.get('/report', (req, res) => {
  res.json({ skus: inventory.length, value: totalValue().toFixed(2) });
});

app.use((req, res) => {
  res.status(404).json({ error: 'route not found' });
});

app.use((err, req, res, next) => {
  console.error(err);
  res.status(500).json({ error: 'internal server error' });
});

app.listen(PORT, () => {
  console.log(`inventory api listening on port ${PORT}`);
});

module.exports = app;
