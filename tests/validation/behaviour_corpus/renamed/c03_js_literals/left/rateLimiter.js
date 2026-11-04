'use strict';

const DEFAULT_WINDOW_MS = 60000;
const DEFAULT_MAX_REQUESTS = 100;
const BURST_MULTIPLIER = 1.5;
const CLEANUP_INTERVAL_MS = 300000;

class RateLimiter {
  constructor(options = {}) {
    this.windowMs = options.windowMs || DEFAULT_WINDOW_MS;
    this.maxRequests = options.maxRequests || DEFAULT_MAX_REQUESTS;
    this.burst = Math.floor(this.maxRequests * BURST_MULTIPLIER);
    this.buckets = new Map();
    this.blocked = new Set();
    this.timer = setInterval(() => this.cleanup(), CLEANUP_INTERVAL_MS);
  }

  key(req) {
    const forwarded = req.headers['x-forwarded-for'];
    if (forwarded) {
      return forwarded.split(',')[0].trim();
    }
    return req.socket ? req.socket.remoteAddress : 'unknown';
  }

  hit(clientId, now = Date.now()) {
    if (this.blocked.has(clientId)) {
      return { allowed: false, reason: 'blocked', retryAfter: -1 };
    }
    let bucket = this.buckets.get(clientId);
    if (!bucket || now - bucket.start >= this.windowMs) {
      bucket = { start: now, count: 0 };
      this.buckets.set(clientId, bucket);
    }
    bucket.count += 1;
    if (bucket.count > this.burst) {
      this.blocked.add(clientId);
      return { allowed: false, reason: 'burst exceeded', retryAfter: -1 };
    }
    if (bucket.count > this.maxRequests) {
      const retryAfter = Math.ceil((bucket.start + this.windowMs - now) / 1000);
      return { allowed: false, reason: 'rate limited', retryAfter };
    }
    return { allowed: true, remaining: this.maxRequests - bucket.count };
  }

  unblock(clientId) {
    return this.blocked.delete(clientId);
  }

  cleanup(now = Date.now()) {
    let removed = 0;
    for (const [clientId, bucket] of this.buckets) {
      if (now - bucket.start > this.windowMs * 2) {
        this.buckets.delete(clientId);
        removed += 1;
      }
    }
    return removed;
  }

  stats() {
    let active = 0;
    let throttled = 0;
    for (const bucket of this.buckets.values()) {
      active += 1;
      if (bucket.count > this.maxRequests) {
        throttled += 1;
      }
    }
    return { active, throttled, blocked: this.blocked.size };
  }

  stop() {
    clearInterval(this.timer);
  }
}

function middleware(limiter) {
  return function rateLimit(req, res, next) {
    const id = limiter.key(req);
    const verdict = limiter.hit(id);
    if (verdict.allowed) {
      res.setHeader('X-RateLimit-Remaining', String(verdict.remaining));
      return next();
    }
    if (verdict.retryAfter > 0) {
      res.setHeader('Retry-After', String(verdict.retryAfter));
    }
    res.statusCode = 429;
    res.end(JSON.stringify({ error: 'Too Many Requests', detail: verdict.reason }));
    return undefined;
  };
}

module.exports = { RateLimiter, middleware };
