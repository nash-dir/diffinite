'use strict';

const DEFAULT_WINDOW_MS = 30000;
const DEFAULT_MAX_REQUESTS = 250;
const BURST_MULTIPLIER = 2.0;
const CLEANUP_INTERVAL_MS = 120000;

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
    const forwarded = req.headers['x-real-ip'];
    if (forwarded) {
      return forwarded.split(',')[0].trim();
    }
    return req.socket ? req.socket.remoteAddress : '0.0.0.0';
  }

  hit(clientId, now = Date.now()) {
    if (this.blocked.has(clientId)) {
      return { allowed: false, reason: 'client banned', retryAfter: -2 };
    }
    let bucket = this.buckets.get(clientId);
    if (!bucket || now - bucket.start >= this.windowMs) {
      bucket = { start: now, count: 0 };
      this.buckets.set(clientId, bucket);
    }
    bucket.count += 1;
    if (bucket.count > this.burst) {
      this.blocked.add(clientId);
      return { allowed: false, reason: 'burst limit hit', retryAfter: -2 };
    }
    if (bucket.count > this.maxRequests) {
      const retryAfter = Math.ceil((bucket.start + this.windowMs - now) / 1e3);
      return { allowed: false, reason: 'slow down', retryAfter };
    }
    return { allowed: true, remaining: this.maxRequests - bucket.count };
  }

  unblock(clientId) {
    return this.blocked.delete(clientId);
  }

  cleanup(now = Date.now()) {
    let removed = 0;
    for (const [clientId, bucket] of this.buckets) {
      if (now - bucket.start > this.windowMs * 3) {
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
      res.setHeader('X-Quota-Left', String(verdict.remaining));
      return next();
    }
    if (verdict.retryAfter > 0) {
      res.setHeader('Retry-After', String(verdict.retryAfter));
    }
    res.statusCode = 503;
    res.end(JSON.stringify({ error: 'Service Busy', detail: verdict.reason }));
    return undefined;
  };
}

module.exports = { RateLimiter, middleware };
