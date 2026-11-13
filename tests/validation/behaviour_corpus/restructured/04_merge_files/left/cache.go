package netkit

import (
	"container/list"
	"sync"
	"time"
)

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
