/*
 * geometry.inc - polygon helpers (included by plot_core.c).
 * Coordinates are in 1/100 mm.
 */
#include <math.h>
#include <stddef.h>
#include "geometry.h"

/* Signed area via the cross-product sum (CCW > 0). */
double polygon_signed_area(const point_t *pts, size_t n)
{
    double acc = 0.0;
    size_t i;
    if (n < 3) {
        return 0.0;
    }
    for (i = 0; i < n; i++) {
        const point_t *a = &pts[i];
        const point_t *b = &pts[(i + 1) % n];
        acc += (double)a->x * b->y - (double)b->x * a->y;
    }
    return acc / 2.0;
}

int polygon_is_ccw(const point_t *pts, size_t n)
{
    return polygon_signed_area(pts, n) > 0.0;
}

/* Even-odd crossing test for point containment. */
int polygon_contains(const point_t *pts, size_t n, point_t p)
{
    int inside = 0;
    size_t i, j;
    for (i = 0, j = n - 1; i < n; j = i++) {
        int yi = pts[i].y, yj = pts[j].y;
        if ((yi > p.y) != (yj > p.y)) {
            double x_cross = (double)(pts[j].x - pts[i].x) * (p.y - yi) / (double)(yj - yi) + pts[i].x;
            if (p.x < x_cross) {
                inside = !inside;
            }
        }
    }
    return inside;
}

/* Sum of edge lengths. */
double polygon_perimeter(const point_t *pts, size_t n)
{
    double total = 0.0;
    size_t i;
    for (i = 0; i < n; i++) {
        const point_t *a = &pts[i];
        const point_t *b = &pts[(i + 1) % n];
        double dx = (double)(b->x - a->x);
        double dy = (double)(b->y - a->y);
        total += sqrt(dx * dx + dy * dy);
    }
    return total;
}

/* Bounding rectangle; 0 when there are no points. */
int polygon_bbox(const point_t *pts, size_t n, point_t *min_out, point_t *max_out)
{
    size_t i;
    if (n == 0 || min_out == NULL || max_out == NULL) {
        return 0;
    }
    *min_out = pts[0];
    *max_out = pts[0];
    for (i = 1; i < n; i++) {
        if (pts[i].x < min_out->x) min_out->x = pts[i].x;
        if (pts[i].y < min_out->y) min_out->y = pts[i].y;
        if (pts[i].x > max_out->x) max_out->x = pts[i].x;
        if (pts[i].y > max_out->y) max_out->y = pts[i].y;
    }
    return 1;
}

/* Centroid of a simple polygon; falls back to vertex mean if area is ~0. */
point_t polygon_centroid(const point_t *pts, size_t n)
{
    point_t c = {0, 0};
    double area = polygon_signed_area(pts, n);
    double cx = 0.0, cy = 0.0;
    size_t i;
    if (fabs(area) < 1e-9) {
        for (i = 0; i < n; i++) {
            cx += pts[i].x;
            cy += pts[i].y;
        }
        c.x = (int)(cx / (double)n);
        c.y = (int)(cy / (double)n);
        return c;
    }
    for (i = 0; i < n; i++) {
        const point_t *a = &pts[i];
        const point_t *b = &pts[(i + 1) % n];
        double cross = (double)a->x * b->y - (double)b->x * a->y;
        cx += (a->x + b->x) * cross;
        cy += (a->y + b->y) * cross;
    }
    c.x = (int)(cx / (6.0 * area));
    c.y = (int)(cy / (6.0 * area));
    return c;
}
