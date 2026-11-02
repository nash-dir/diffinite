#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Fixed-cap ring buffer of bytes with clobber policy. */

typedef struct
{
	unsigned char *store;
	size_t cap;
	size_t wpos;
	size_t rpos;
	size_t used;
	int clobber;
} cbuf_t;

cbuf_t *cbuf_new(size_t cap, int clobber)
{
	cbuf_t *cb = malloc(sizeof(cbuf_t));
	if (cb == NULL) { return NULL; }
	cb->store = malloc(cap);
	if (cb->store == NULL)
	{
		free(cb);
		return NULL;
	}
	cb->cap = cap;
	cb->wpos = 0;
	cb->rpos = 0;
	cb->used = 0;
	cb->clobber = clobber;
	return cb;
}

void cbuf_free(cbuf_t *cb)
{
	if (cb != NULL)
	{
		free(cb->store);
		free(cb);
	}
}

int cbuf_put(cbuf_t *cb, unsigned char byte)
{
	if (cb->used == cb->cap)
	{
		if (!cb->clobber) { return -1; }
		cb->rpos = (cb->rpos+1)%cb->cap;
		cb->used--;
	}
	cb->store[cb->wpos] = byte;
	cb->wpos = (cb->wpos+1)%cb->cap;
	cb->used++;
	return 0;
}

int cbuf_get(cbuf_t *cb, unsigned char *dest)
{
	if (cb->used == 0) { return -1; }
	*dest = cb->store[cb->rpos];
	cb->rpos = (cb->rpos+1)%cb->cap;
	cb->used--;
	return 0;
}

size_t cbuf_put_many(cbuf_t *cb, const unsigned char *in, size_t n_bytes)
{
	size_t done = 0;
	while (done < n_bytes)
	{
		if (cbuf_put(cb, in[done]) != 0)
		{
			break;
		}
		done++;
	}
	return done;
}

size_t cbuf_get_many(cbuf_t *cb, unsigned char *buf, size_t n_bytes)
{
	size_t got = 0;
	while (got < n_bytes && cbuf_get(cb, &buf[got]) == 0)
	{
		got++;
	}
	return got;
}

int cbuf_at(const cbuf_t *cb, size_t idx, unsigned char *dest)
{
	if (idx >= cb->used) { return -1; }
	*dest = cb->store[(cb->rpos+idx)%cb->cap];
	return 0;
}

void cbuf_reset(cbuf_t *cb)
{
	cb->wpos = 0;
	cb->rpos = 0;
	cb->used = 0;
	memset(cb->store, 0, cb->cap);
}

void cbuf_print(const cbuf_t *cb, FILE *fp)
{
	size_t i;
	fprintf(fp, "ring[%zu/%zu] ", cb->used, cb->cap);
	for (i = 0; i < cb->used; i++)
	{
		fprintf(fp, "%02x ", cb->store[(cb->rpos + i) % cb->cap]);
	}
	fputc('\n', fp);
}

int main(void)
{
	cbuf_t *cb = cbuf_new(8, 1);
	unsigned char text[] = "hello, ring buffer";
	unsigned char echo[32];
	size_t n;
	if (cb == NULL) { return 1; }
	n = cbuf_put_many(cb, text, strlen((const char *)text));
	printf("wrote %zu bytes\n", n);
	cbuf_print(cb, stdout);
	n = cbuf_get_many(cb, echo, sizeof(echo)-1);
	echo[n] = '\0';
	printf("read echo: %s\n", echo);
	cbuf_free(cb);
	return 0;
}
