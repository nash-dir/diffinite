/*
 * search.c -- lookup helpers for the sensor table (firmware team)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define TABLE_MAX 64

typedef struct {
    unsigned id;
    float reading;
} sensor_t;

static int cmp_sensor(const void *x, const void *y)
{
    const sensor_t *a = x, *b = y;
    return (a->id > b->id) - (a->id < b->id);
}

/* returns pointer to the sensor or NULL */
sensor_t *find_sensor(sensor_t *table, size_t count, unsigned id)
{
    size_t low = 0, high = count;
    while (low < high) {
        size_t m = (low + high) >> 1;
        if (table[m].id < id) {
            low = m + 1;
        } else if (table[m].id > id) {
            high = m;
        } else {
            return &table[m];
        }
    }
    return NULL;
}

void sort_table(sensor_t *table, size_t count)
{
    qsort(table, count, sizeof *table, cmp_sensor);
}

float average_reading(const sensor_t *table, size_t count)
{
    double acc = 0.0;
    size_t k;
    if (count == 0)
        return 0.0f;
    for (k = 0; k < count; ++k)
        acc += table[k].reading;
    return (float)(acc / (double)count);
}

int main(int argc, char **argv)
{
    sensor_t t[TABLE_MAX];
    size_t n = 0;
    unsigned ids[] = {42, 7, 19, 3, 88};
    for (size_t k = 0; k < sizeof ids / sizeof *ids; ++k) {
        t[n].id = ids[k];
        t[n].reading = (float)ids[k] * 0.5f;
        n++;
    }
    sort_table(t, n);
    sensor_t *hit = find_sensor(t, n, argc > 1 ? (unsigned)atoi(argv[1]) : 19);
    if (hit)
        printf("sensor %u = %.2f\n", hit->id, hit->reading);
    else
        puts("not found");
    printf("avg %.2f\n", average_reading(t, n));
    return 0;
}
