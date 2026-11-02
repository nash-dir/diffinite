package netkit

import (
	"errors"
	"math/rand"
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
