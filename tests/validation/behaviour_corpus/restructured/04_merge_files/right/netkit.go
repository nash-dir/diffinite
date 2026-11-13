// Package netkit bundles small networking helpers in a single file.
package netkit

import (
	"container/list"
	"errors"
	"math/rand"
	"sync"
	"time"
)

// ErrGiveUp is returned when all retry attempts are exhausted.
var ErrGiveUp = errors.New("netkit: retries exhausted")

// RetryPolicy configures exponential backoff with jitter.
type RetryPolicy struct {
	MaxAttempts int
	BaseDelay   time.Duration
	MaxDelay    time.Duration
	Jitter      float64
}

// DefaultRetryPolicy is suitable for idempotent HTTP calls.
var DefaultRetryPolicy = RetryPolicy{
	MaxAttempts: 5,
	BaseDelay:   100 * time.Millisecond,
	MaxDelay:    5 * time.Second,
	Jitter:      0.2,
}

func (p RetryPolicy) delay(attempt int) time.Duration {
	d := p.BaseDelay << uint(attempt)
	if d > p.MaxDelay || d <= 0 {
		d = p.MaxDelay
	}
	if p.Jitter > 0 {
		spread := float64(d) * p.Jitter
		d = time.Duration(float64(d) - spread + rand.Float64()*2*spread)
	}
	return d
}

// Retryable lets callers mark errors that must not be retried.
type Retryable interface {
	Temporary() bool
}

func shouldRetry(err error) bool {
	var r Retryable
	if errors.As(err, &r) {
		return r.Temporary()
	}
	return true
}

// Do runs fn until it succeeds, returns a permanent error, or attempts run out.
func (p RetryPolicy) Do(fn func(attempt int) error) error {
	var last error
	for attempt := 0; attempt < p.MaxAttempts; attempt++ {
		err := fn(attempt)
		if err == nil {
			return nil
		}
		last = err
		if !shouldRetry(err) {
			return err
		}
		if attempt+1 < p.MaxAttempts {
			time.Sleep(p.delay(attempt))
		}
	}
	return errors.Join(ErrGiveUp, last)
}

type entry struct {
	key     string
	value   []byte
	expires time.Time
}

// LRUCache is a size-bounded cache with per-entry TTL.
type LRUCache struct {
	mu      sync.Mutex
	maxSize int
	ttl     time.Duration
	order   *list.List
	index   map[string]*list.Element
	hits    uint64
	misses  uint64
}

// NewLRUCache builds an empty cache.
func NewLRUCache(maxSize int, ttl time.Duration) *LRUCache {
	return &LRUCache{
		maxSize: maxSize,
		ttl:     ttl,
		order:   list.New(),
		index:   make(map[string]*list.Element),
	}
}

// Get returns the cached value if present and not expired.
func (c *LRUCache) Get(key string) ([]byte, bool) {
	c.mu.Lock()
	defer c.mu.Unlock()
	el, ok := c.index[key]
	if !ok {
		c.misses++
		return nil, false
	}
	e := el.Value.(*entry)
	if time.Now().After(e.expires) {
		c.order.Remove(el)
		delete(c.index, key)
		c.misses++
		return nil, false
	}
	c.order.MoveToFront(el)
	c.hits++
	return e.value, true
}

// Put inserts or replaces a value, evicting the oldest entries when full.
func (c *LRUCache) Put(key string, value []byte) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if el, ok := c.index[key]; ok {
		e := el.Value.(*entry)
		e.value = value
		e.expires = time.Now().Add(c.ttl)
		c.order.MoveToFront(el)
		return
	}
	el := c.order.PushFront(&entry{key: key, value: value, expires: time.Now().Add(c.ttl)})
	c.index[key] = el
	for c.order.Len() > c.maxSize {
		oldest := c.order.Back()
		if oldest == nil {
			break
		}
		c.order.Remove(oldest)
		delete(c.index, oldest.Value.(*entry).key)
	}
}

// Stats returns the hit and miss counters.
func (c *LRUCache) Stats() (hits, misses uint64) {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.hits, c.misses
}

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
