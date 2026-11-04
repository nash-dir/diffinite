// Copyright (c) 2025 Acme Embedded Ltd. All rights reserved.
// Module: serial receive queue (circular byte FIFO).
// Author: J. Park
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "ringbuf.h"

struct ringbuf {
    uint8_t *data;
    size_t cap;
    size_t head;
    size_t tail;
    uint32_t overflows;
};

// Creates a FIFO. Caller owns the result and must call rb_destroy().
// Returns NULL when memory is exhausted.
ringbuf_t *rb_create(size_t capacity)
{
    ringbuf_t *rb = malloc(sizeof(*rb));
    if (rb == NULL) {
        return NULL;
    }
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

// Releases all memory held by the FIFO. NULL is accepted.
void rb_destroy(ringbuf_t *rb)
{
    if (rb == NULL) {
        return;
    }
    free(rb->data);
    free(rb);
}

// Number of bytes currently stored.
size_t rb_used(const ringbuf_t *rb)
{
    if (rb->head >= rb->tail) {
        return rb->head - rb->tail;
    }
    return rb->cap - rb->tail + rb->head;
}

// Remaining room in bytes.
size_t rb_free(const ringbuf_t *rb)
{
    return rb->cap - 1 - rb_used(rb);
}

// Enqueue one byte. Fails with -1 when there is no room.
int rb_put(ringbuf_t *rb, uint8_t byte)
{
    size_t next = (rb->head + 1) % rb->cap;
    if (next == rb->tail) {
        rb->overflows++;
        return -1;
    }
    rb->data[rb->head] = byte;
    rb->head = next;
    return 0;
}

// Dequeue one byte. Fails with -1 when nothing is queued.
int rb_get(ringbuf_t *rb, uint8_t *out)
{
    if (rb->head == rb->tail) {
        return -1;
    }
    *out = rb->data[rb->tail];
    rb->tail = (rb->tail + 1) % rb->cap;
    return 0;
}

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
        rb->overflows += (uint32_t)(len - n);  // track how many bytes were lost
    }
    return n;
}

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

// Peek-search for `delim`. Index relative to read position, or -1.
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

/* TODO: should this also reset the overflow counter? */
void rb_clear(ringbuf_t *rb)
{
    rb->head = rb->tail = 0;
}
