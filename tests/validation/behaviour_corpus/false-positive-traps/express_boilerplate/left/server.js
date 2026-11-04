'use strict';

const express = require('express');
const helmet = require('helmet');
const cors = require('cors');
const morgan = require('morgan');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(helmet());
app.use(cors());
app.use(express.json());
app.use(morgan('dev'));

// in-memory store of short links
const links = new Map();
let hits = 0;

function makeCode(len = 6) {
  const alphabet = 'abcdefghijkmnpqrstuvwxyz23456789';
  let out = '';
  for (let i = 0; i < len; i++) {
    out += alphabet[Math.floor(Math.random() * alphabet.length)];
  }
  return out;
}

function isValidUrl(s) {
  try {
    const u = new URL(s);
    return u.protocol === 'http:' || u.protocol === 'https:';
  } catch (e) {
    return false;
  }
}

app.get('/healthz', (req, res) => {
  res.json({ status: 'ok', links: links.size, hits });
});

app.post('/api/links', (req, res) => {
  const { url, code } = req.body || {};
  if (!isValidUrl(url)) {
    return res.status(400).json({ error: 'invalid url' });
  }
  const key = code || makeCode();
  if (links.has(key)) {
    return res.status(409).json({ error: 'code already taken' });
  }
  links.set(key, { url, created: Date.now(), visits: 0 });
  res.status(201).json({ code: key, short: `/${key}` });
});

app.get('/api/links/:code', (req, res) => {
  const entry = links.get(req.params.code);
  if (!entry) return res.status(404).json({ error: 'not found' });
  res.json({ code: req.params.code, ...entry });
});

app.delete('/api/links/:code', (req, res) => {
  if (!links.delete(req.params.code)) {
    return res.status(404).json({ error: 'not found' });
  }
  res.status(204).end();
});

app.get('/:code', (req, res, next) => {
  const entry = links.get(req.params.code);
  if (!entry) return next();
  entry.visits += 1;
  hits += 1;
  res.redirect(302, entry.url);
});

app.use((req, res) => {
  res.status(404).json({ error: 'route not found' });
});

app.use((err, req, res, next) => {
  console.error(err);
  res.status(500).json({ error: 'internal server error' });
});

app.listen(PORT, () => {
  console.log(`shortener listening on http://localhost:${PORT}`);
});

module.exports = app;
