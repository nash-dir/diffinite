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
        char *start = line;
        char *end;
        char *eq;
        lineno++;

        /* trim leading whitespace */
        while (*start && isspace((unsigned char)*start)) {
            start++;
        }
        /* trim trailing whitespace */
        end = start + strlen(start);
        while (end > start && isspace((unsigned char)end[-1])) {
            end--;
        }
        *end = '\0';

        if (*start == '\0' || *start == '#' || *start == ';') {
            continue;
        }

        if (*start == '[') {
            char *close = strchr(start, ']');
            if (close == NULL) {
                fprintf(stderr, "%s:%d: unterminated section\n", path, lineno);
                cfg->errors++;
                continue;
            }
            *close = '\0';
            strncpy(section, start + 1, MAX_KEY - 1);
            section[MAX_KEY - 1] = '\0';
            continue;
        }

        eq = strchr(start, '=');
        if (eq == NULL) {
            fprintf(stderr, "%s:%d: expected key = value\n", path, lineno);
            cfg->errors++;
            continue;
        }
        *eq = '\0';
        {
            char *k = start;
            char *v = eq + 1;
            char *kend = eq;
            config_entry *e;

            while (kend > k && isspace((unsigned char)kend[-1])) {
                kend--;
            }
            *kend = '\0';
            while (*v && isspace((unsigned char)*v)) {
                v++;
            }
            if (*v == '"') {
                size_t vlen = strlen(v);
                if (vlen >= 2 && v[vlen - 1] == '"') {
                    v[vlen - 1] = '\0';
                    v++;
                }
            }
            if (cfg->count >= MAX_ENTRIES) {
                fprintf(stderr, "%s:%d: too many entries\n", path, lineno);
                cfg->errors++;
                break;
            }
            e = &cfg->entries[cfg->count++];
            strncpy(e->section, section, MAX_KEY - 1);
            e->section[MAX_KEY - 1] = '\0';
            strncpy(e->key, k, MAX_KEY - 1);
            e->key[MAX_KEY - 1] = '\0';
            strncpy(e->value, v, MAX_VALUE - 1);
            e->value[MAX_VALUE - 1] = '\0';
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

int config_get_bool(const config_t *cfg, const char *section, const char *key, int fallback)
{
    const char *raw = config_get(cfg, section, key);
    if (raw == NULL) {
        return fallback;
    }
    if (strcmp(raw, "1") == 0 || strcmp(raw, "true") == 0 || strcmp(raw, "yes") == 0 || strcmp(raw, "on") == 0) {
        return 1;
    }
    if (strcmp(raw, "0") == 0 || strcmp(raw, "false") == 0 || strcmp(raw, "no") == 0 || strcmp(raw, "off") == 0) {
        return 0;
    }
    return fallback;
}
