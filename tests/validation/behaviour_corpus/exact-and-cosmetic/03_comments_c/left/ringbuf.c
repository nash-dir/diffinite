/*
 * ringbuf.c - fixed-capacity byte ring buffer for UART RX handling.
 *
 * The buffer keeps one slot empty so that head == tail always means
 * "empty" and (head + 1) % cap == tail means "full".
 */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "ringbuf.h"

struct ringbuf {
    uint8_t *data;      /* backing storage */
    size_t cap;         /* total slots, one is always unused */
    size_t head;        /* next write position */
    size_t tail;        /* next read position */
    uint32_t overflows; /* count of dropped bytes */
};

/* Allocate a new ring buffer able to hold `capacity` bytes. */
ringbuf_t *rb_create(size_t capacity)
{
    ringbuf_t *rb = malloc(sizeof(*rb));
    if (rb == NULL) {
        return NULL;
    }
    /* one extra slot for the full/empty distinction */
    rb->data = malloc(capacity + 1);
    if (rb->data == NULL) {
        free(rb);
        return NULL;
    }
    rb->cap = capacity + 1;
    rb->head = 0;
    rb->tail = 0;
    rb->overflows = 0;
    return rb;
}

void rb_destroy(ringbuf_t *rb)
{
    if (rb == NULL) {
        return;
    }
    free(rb->data);
    free(rb);
}

size_t rb_used(const ringbuf_t *rb)
{
    if (rb->head >= rb->tail) {
        return rb->head - rb->tail;
    }
    return rb->cap - rb->tail + rb->head;
}

size_t rb_free(const ringbuf_t *rb)
{
    return rb->cap - 1 - rb_used(rb);
}

/* Push a single byte; returns 0 on success, -1 if the buffer was full. */
int rb_put(ringbuf_t *rb, uint8_t byte)
{
    size_t next = (rb->head + 1) % rb->cap;
    if (next == rb->tail) {
        rb->overflows++;   /* caller is too slow draining */
        return -1;
    }
    rb->data[rb->head] = byte;
    rb->head = next;
    return 0;
}

/* Pop a single byte into *out; returns 0 on success, -1 if empty. */
int rb_get(ringbuf_t *rb, uint8_t *out)
{
    if (rb->head == rb->tail) {
        return -1;
    }
    *out = rb->data[rb->tail];
    rb->tail = (rb->tail + 1) % rb->cap;
    return 0;
}

/*
 * Bulk write. Copies as many bytes as fit and returns the count copied.
 * Uses at most two memcpy calls to handle the wrap-around.
 */
size_t rb_write(ringbuf_t *rb, const uint8_t *src, size_t len)
{
    size_t n = len < rb_free(rb) ? len : rb_free(rb);
    size_t first = rb->cap - rb->head;
    if (first > n) {
        first = n;
    }
    memcpy(rb->data + rb->head, src, first);
    memcpy(rb->data, src + first, n - first);
    rb->head = (rb->head + n) % rb->cap;
    if (n < len) {
        rb->overflows += (uint32_t)(len - n);
    }
    return n;
}

/* Bulk read; mirror image of rb_write. */
size_t rb_read(ringbuf_t *rb, uint8_t *dst, size_t len)
{
    size_t n = len < rb_used(rb) ? len : rb_used(rb);
    size_t first = rb->cap - rb->tail;
    if (first > n) {
        first = n;
    }
    memcpy(dst, rb->data + rb->tail, first);
    memcpy(dst + first, rb->data, n - first);
    rb->tail = (rb->tail + n) % rb->cap;
    return n;
}

/* Look for a delimiter without consuming; returns index or -1. */
long rb_find(const ringbuf_t *rb, uint8_t delim)
{
    size_t used = rb_used(rb);
    size_t i;
    for (i = 0; i < used; i++) {
        if (rb->data[(rb->tail + i) % rb->cap] == delim) {
            return (long)i;
        }
    }
    return -1;
}

uint32_t rb_overflows(const ringbuf_t *rb)
{
    return rb->overflows;
}

void rb_clear(ringbuf_t *rb)
{
    rb->head = rb->tail = 0;
}
