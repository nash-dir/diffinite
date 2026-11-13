#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_LINE 512
#define MAX_KEY 64
#define MAX_VALUE 256
#define MAX_ENTRIES 128

typedef struct {
    char section[MAX_KEY];
    char key[MAX_KEY];
    char value[MAX_VALUE];
} config_entry;

typedef struct {
    config_entry entries[MAX_ENTRIES];
    int count;
    int errors;
} config_t;

static char *trim(char *start)
{
    char *end;
    while (*start && isspace((unsigned char)*start)) {
        start++;
    }
    end = start + strlen(start);
    while (end > start && isspace((unsigned char)end[-1])) {
        end--;
    }
    *end = '\0';
    return start;
}

static void copy_field(char *dst, const char *src, size_t cap)
{
    strncpy(dst, src, cap - 1);
    dst[cap - 1] = '\0';
}

static char *unquote(char *v)
{
    if (*v == '"') {
        size_t vlen = strlen(v);
        if (vlen >= 2 && v[vlen - 1] == '"') {
            v[vlen - 1] = '\0';
            v++;
        }
    }
    return v;
}

static int parse_section(char *start, char *section, const char *path, int lineno)
{
    char *close = strchr(start, ']');
    if (close == NULL) {
        fprintf(stderr, "%s:%d: unterminated section\n", path, lineno);
        return -1;
    }
    *close = '\0';
    copy_field(section, start + 1, MAX_KEY);
    return 0;
}

static int add_entry(config_t *cfg, const char *section, const char *k, const char *v)
{
    config_entry *e;
    if (cfg->count >= MAX_ENTRIES) {
        return -1;
    }
    e = &cfg->entries[cfg->count++];
    copy_field(e->section, section, MAX_KEY);
    copy_field(e->key, k, MAX_KEY);
    copy_field(e->value, v, MAX_VALUE);
    return 0;
}

static int parse_pair(config_t *cfg, char *start, const char *section, const char *path, int lineno)
{
    char *eq = strchr(start, '=');
    char *k;
    char *v;
    if (eq == NULL) {
        fprintf(stderr, "%s:%d: expected key = value\n", path, lineno);
        return -1;
    }
    *eq = '\0';
    k = trim(start);
    v = unquote(trim(eq + 1));
    if (add_entry(cfg, section, k, v) != 0) {
        fprintf(stderr, "%s:%d: too many entries\n", path, lineno);
        return -2;
    }
    return 0;
}

int config_load(config_t *cfg, const char *path)
{
    FILE *fp;
    char line[MAX_LINE];
    char section[MAX_KEY] = "global";
    int lineno = 0;

    cfg->count = 0;
    cfg->errors = 0;
    fp = fopen(path, "r");
    if (fp == NULL) {
        perror(path);
        return -1;
    }

    while (fgets(line, sizeof(line), fp) != NULL) {
        char *start = trim(line);
        int rc;
        lineno++;

        if (*start == '\0' || *start == '#' || *start == ';') {
            continue;
        }
        if (*start == '[') {
            if (parse_section(start, section, path, lineno) != 0) {
                cfg->errors++;
            }
            continue;
        }
        rc = parse_pair(cfg, start, section, path, lineno);
        if (rc != 0) {
            cfg->errors++;
            if (rc == -2) {
                break;
            }
        }
    }

    fclose(fp);
    return cfg->errors == 0 ? 0 : 1;
}

const char *config_get(const config_t *cfg, const char *section, const char *key)
{
    int i;
    for (i = cfg->count - 1; i >= 0; i--) {
        const config_entry *e = &cfg->entries[i];
        if (strcmp(e->section, section) == 0 && strcmp(e->key, key) == 0) {
            return e->value;
        }
    }
    return NULL;
}

long config_get_int(const config_t *cfg, const char *section, const char *key, long fallback)
{
    const char *raw = config_get(cfg, section, key);
    char *endp;
    long val;
    if (raw == NULL || *raw == '\0') {
        return fallback;
    }
    val = strtol(raw, &endp, 0);
    if (*endp != '\0') {
        return fallback;
    }
    return val;
}

static int matches_any(const char *raw, const char *const *words)
{
    for (; *words != NULL; words++) {
        if (strcmp(raw, *words) == 0) {
            return 1;
        }
    }
    return 0;
}

int config_get_bool(const config_t *cfg, const char *section, const char *key, int fallback)
{
    static const char *const truthy[] = { "1", "true", "yes", "on", NULL };
    static const char *const falsy[] = { "0", "false", "no", "off", NULL };
    const char *raw = config_get(cfg, section, key);
    if (raw == NULL) {
        return fallback;
    }
    if (matches_any(raw, truthy)) {
        return 1;
    }
    if (matches_any(raw, falsy)) {
        return 0;
    }
    return fallback;
}
