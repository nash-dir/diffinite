"""Layered configuration loader: defaults < file < environment."""

import json
import os

DEFAULTS = {
    "server": {"host": "127.0.0.1", "port": 8080, "workers": 2},
    "db": {"url": "sqlite:///app.db", "pool_size": 5, "echo": False},
    "features": {"beta_ui": False, "audit": True},
}

ENV_PREFIX = "APP__"


def deep_merge(base, override):
    """Recursively merge override into a copy of base."""
    result = {}
    for key in set(base) | set(override):
        if key in base and key in override:
            if isinstance(base[key], dict) and isinstance(override[key], dict):
                result[key] = deep_merge(base[key], override[key])
            else:
                result[key] = override[key]
        elif key in override:
            result[key] = override[key]
        else:
            result[key] = base[key]
    return result


def coerce(value, template):
    """Convert an env string to the type of the default value."""
    if isinstance(template, bool):
        return value.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(template, int):
        return int(value)
    if isinstance(template, float):
        return float(value)
    return value


def from_environment(defaults, environ=None):
    environ = os.environ if environ is None else environ
    overrides = {}
    for name, raw in environ.items():
        if not name.startswith(ENV_PREFIX):
            continue
        path = name[len(ENV_PREFIX):].lower().split("__")
        node = defaults
        for part in path[:-1]:
            node = node.get(part, {}) if isinstance(node, dict) else {}
        template = node.get(path[-1], "") if isinstance(node, dict) else ""
        target = overrides
        for part in path[:-1]:
            target = target.setdefault(part, {})
        target[path[-1]] = coerce(raw, template)
    return overrides


def load(path=None, environ=None):
    config = dict(DEFAULTS)
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            config = deep_merge(config, json.load(fh))
    config = deep_merge(config, from_environment(DEFAULTS, environ))
    validate(config)
    return config


def validate(config):
    port = config["server"]["port"]
    if not (0 < port < 65536):
        raise ValueError("server.port out of range: %r" % port)
    if config["db"]["pool_size"] < 1:
        raise ValueError("db.pool_size must be >= 1")
