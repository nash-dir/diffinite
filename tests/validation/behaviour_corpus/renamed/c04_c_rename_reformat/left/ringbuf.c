#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Fixed-capacity ring buffer of bytes with overwrite policy. */

typedef struct {
    unsigned char *data;
    size_t capacity;
    size_t head;
    size_t tail;
    size_t size;
    int overwrite;
} ring_buffer;

ring_buffer *rb_create(size_t capacity, int overwrite) {
    ring_buffer *rb = malloc(sizeof(ring_buffer));
    if (rb == NULL) {
        return NULL;
    }
    rb->data = malloc(capacity);
    if (rb->data == NULL) {
        free(rb);
        return NULL;
    }
    rb->capacity = capacity;
    rb->head = 0;
    rb->tail = 0;
    rb->size = 0;
    rb->overwrite = overwrite;
    return rb;
}

void rb_destroy(ring_buffer *rb) {
    if (rb != NULL) {
        free(rb->data);
        free(rb);
    }
}

int rb_push(ring_buffer *rb, unsigned char value) {
    if (rb->size == rb->capacity) {
        if (!rb->overwrite) {
            return -1;
        }
        rb->tail = (rb->tail + 1) % rb->capacity;
        rb->size--;
    }
    rb->data[rb->head] = value;
    rb->head = (rb->head + 1) % rb->capacity;
    rb->size++;
    return 0;
}

int rb_pop(ring_buffer *rb, unsigned char *out) {
    if (rb->size == 0) {
        return -1;
    }
    *out = rb->data[rb->tail];
    rb->tail = (rb->tail + 1) % rb->capacity;
    rb->size--;
    return 0;
}

size_t rb_write(ring_buffer *rb, const unsigned char *src, size_t len) {
    size_t written = 0;
    while (written < len) {
        if (rb_push(rb, src[written]) != 0) {
            break;
        }
        written++;
    }
    return written;
}

size_t rb_read(ring_buffer *rb, unsigned char *dst, size_t len) {
    size_t count = 0;
    while (count < len && rb_pop(rb, &dst[count]) == 0) {
        count++;
    }
    return count;
}

int rb_peek(const ring_buffer *rb, size_t offset, unsigned char *out) {
    if (offset >= rb->size) {
        return -1;
    }
    *out = rb->data[(rb->tail + offset) % rb->capacity];
    return 0;
}

void rb_clear(ring_buffer *rb) {
    rb->head = 0;
    rb->tail = 0;
    rb->size = 0;
    memset(rb->data, 0, rb->capacity);
}

void rb_dump(const ring_buffer *rb, FILE *stream) {
    size_t i;
    fprintf(stream, "ring[%zu/%zu] ", rb->size, rb->capacity);
    for (i = 0; i < rb->size; i++) {
        fprintf(stream, "%02x ", rb->data[(rb->tail + i) % rb->capacity]);
    }
    fputc('\n', stream);
}

int main(void) {
    ring_buffer *rb = rb_create(8, 1);
    unsigned char msg[] = "hello, ring buffer";
    unsigned char back[32];
    size_t n;
    if (rb == NULL) {
        return 1;
    }
    n = rb_write(rb, msg, strlen((const char *)msg));
    printf("wrote %zu bytes\n", n);
    rb_dump(rb, stdout);
    n = rb_read(rb, back, sizeof(back) - 1);
    back[n] = '\0';
    printf("read back: %s\n", back);
    rb_destroy(rb);
    return 0;
}
