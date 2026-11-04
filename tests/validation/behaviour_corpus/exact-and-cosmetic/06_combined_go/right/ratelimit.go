/*
Package ratelimit provides per-client throttling.

Copyright 2026 Example Corp.
*/
package ratelimit

import (
    "errors"
    "sync"
    "time"
)

var ErrLimited = errors.New("ratelimit: too many requests")


type bucket struct {
    tokens float64
    lastFill time.Time
}


type Limiter struct {
    mu sync.Mutex
    rate float64
    burst float64
    buckets map[string]*bucket
    now func() time.Time
    maxIdle time.Duration
    lastScan time.Time
}


// New returns a configured limiter. The map starts empty and grows lazily.
func New(rate float64, burst int) *Limiter {
    return &Limiter{
        rate: rate,
        burst: float64(burst),
        buckets: make(map[string]*bucket),
        now: time.Now,
        maxIdle: 10 * time.Minute,
    }
}


// refill tops up the bucket based on wall-clock time since the last fill.
func (l *Limiter) refill(b *bucket, now time.Time) {
    elapsed := now.Sub(b.lastFill).Seconds()
    if elapsed <= 0 {
        return
    }
    b.tokens += elapsed * l.rate
    if b.tokens > l.burst {
        b.tokens = l.burst
    }
    b.lastFill = now
}


func (l *Limiter) AllowN(key string, n int) bool {
    l.mu.Lock()
    defer l.mu.Unlock()
    now := l.now()
    b, ok := l.buckets[key]
    if !ok {
        b = &bucket{tokens: l.burst, lastFill: now}
        l.buckets[key] = b
    }
    l.refill(b, now)
    l.maybeEvict(now)
    need := float64(n)
    if b.tokens < need {
        return false
    }
    b.tokens -= need
    return true
}


func (l *Limiter) Allow(key string) bool {
    return l.AllowN(key, 1)
}


// Wait polls until allowed; returns ErrLimited once the deadline would be exceeded.
func (l *Limiter) Wait(key string, timeout time.Duration) error {
    deadline := l.now().Add(timeout)
    for {
        if l.Allow(key) {
            return nil
        }
        delay := l.retryAfter(key)
        if l.now().Add(delay).After(deadline) {
            return ErrLimited
        }
        time.Sleep(delay)
    }
}


func (l *Limiter) retryAfter(key string) time.Duration {
    l.mu.Lock()
    defer l.mu.Unlock()
    b, ok := l.buckets[key]
    if !ok || b.tokens >= 1 {
        return 0
    }
    missing := 1 - b.tokens
    return time.Duration(missing / l.rate * float64(time.Second))
}


func (l *Limiter) maybeEvict(now time.Time) {
    if now.Sub(l.lastScan) < l.maxIdle {
        return
    }
    for k, b := range l.buckets {
        if now.Sub(b.lastFill) > l.maxIdle {
            delete(l.buckets, k)
        }
    }
    l.lastScan = now
}


func (l *Limiter) Len() int {
    l.mu.Lock()
    defer l.mu.Unlock()
    return len(l.buckets)
}
