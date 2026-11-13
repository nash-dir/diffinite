// Package ratelimit implements a token-bucket limiter keyed by client.
package ratelimit

import (
	"errors"
	"sync"
	"time"
)

// ErrLimited is returned when a request exceeds the configured rate.
var ErrLimited = errors.New("ratelimit: too many requests")

type bucket struct {
	tokens   float64
	lastFill time.Time
}

// Limiter hands out tokens per key at a fixed refill rate.
type Limiter struct {
	mu       sync.Mutex
	rate     float64 // tokens per second
	burst    float64 // bucket capacity
	buckets  map[string]*bucket
	now      func() time.Time
	maxIdle  time.Duration
	lastScan time.Time
}

// New creates a limiter allowing `rate` events per second with bursts up to `burst`.
func New(rate float64, burst int) *Limiter {
	return &Limiter{
		rate:    rate,
		burst:   float64(burst),
		buckets: make(map[string]*bucket),
		now:     time.Now,
		maxIdle: 10 * time.Minute,
	}
}

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

// AllowN reports whether n events may happen now for key.
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

// Allow is shorthand for AllowN(key, 1).
func (l *Limiter) Allow(key string) bool {
	return l.AllowN(key, 1)
}

// Wait blocks until an event is permitted or the timeout passes.
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

// maybeEvict drops idle buckets at most once per maxIdle interval.
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

// Len returns the number of tracked keys.
func (l *Limiter) Len() int {
	l.mu.Lock()
	defer l.mu.Unlock()
	return len(l.buckets)
}
