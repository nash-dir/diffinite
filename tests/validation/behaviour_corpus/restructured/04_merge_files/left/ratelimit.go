package netkit

import (
	"sync"
	"time"
)

// TokenBucket is a simple thread-safe token bucket rate limiter.
type TokenBucket struct {
	mu       sync.Mutex
	capacity float64
	tokens   float64
	rate     float64 // tokens per second
	last     time.Time
	now      func() time.Time
}

// NewTokenBucket creates a bucket that starts full.
func NewTokenBucket(capacity int, perSecond float64) *TokenBucket {
	return &TokenBucket{
		capacity: float64(capacity),
		tokens:   float64(capacity),
		rate:     perSecond,
		last:     time.Now(),
		now:      time.Now,
	}
}

func (b *TokenBucket) refill() {
	t := b.now()
	elapsed := t.Sub(b.last).Seconds()
	if elapsed <= 0 {
		return
	}
	b.tokens += elapsed * b.rate
	if b.tokens > b.capacity {
		b.tokens = b.capacity
	}
	b.last = t
}

// Allow reports whether n tokens could be taken right now.
func (b *TokenBucket) Allow(n int) bool {
	b.mu.Lock()
	defer b.mu.Unlock()
	b.refill()
	need := float64(n)
	if b.tokens < need {
		return false
	}
	b.tokens -= need
	return true
}

// Wait blocks until n tokens are available or the deadline passes.
func (b *TokenBucket) Wait(n int, deadline time.Time) bool {
	for {
		if b.Allow(n) {
			return true
		}
		b.mu.Lock()
		missing := float64(n) - b.tokens
		b.mu.Unlock()
		sleep := time.Duration(missing / b.rate * float64(time.Second))
		if sleep < time.Millisecond {
			sleep = time.Millisecond
		}
		if time.Now().Add(sleep).After(deadline) {
			return false
		}
		time.Sleep(sleep)
	}
}
