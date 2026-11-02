# textkit 2.1.0 -- small text utilities
# Copyright (c) 2019 Textkit Contributors
# SPDX-License-Identifier: MIT
#
# Vendored copy. Do not modify; update by re-vendoring from upstream.

import re
import unicodedata

__version__ = "2.1.0"

_SLUG_STRIP = re.compile(r"[^\w\s-]", re.UNICODE)
_SLUG_HYPHENATE = re.compile(r"[-\s]+", re.UNICODE)
_WS = re.compile(r"\s+")


def strip_accents(text):
    """Remove combining marks: 'Crème brûlée' -> 'Creme brulee'."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def slugify(value, allow_unicode=False, max_length=0, separator="-"):
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize("NFKC", value)
    else:
        value = strip_accents(value).encode("ascii", "ignore").decode("ascii")
    value = _SLUG_STRIP.sub("", value).strip().lower()
    value = _SLUG_HYPHENATE.sub(separator, value)
    if max_length and len(value) > max_length:
        value = value[:max_length].rstrip(separator)
    return value


def truncate_words(text, count, ellipsis="..."):
    words = text.split()
    if len(words) <= count:
        return text
    return " ".join(words[:count]) + ellipsis


def collapse_whitespace(text):
    return _WS.sub(" ", text).strip()


def wrap(text, width=72):
    lines, current = [], []
    length = 0
    for word in text.split():
        if length + len(word) + len(current) > width and current:
            lines.append(" ".join(current))
            current, length = [], 0
        current.append(word)
        length += len(word)
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


def camel_to_snake(name):
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def snake_to_camel(name, upper_first=False):
    parts = name.split("_")
    head = parts[0].capitalize() if upper_first else parts[0]
    return head + "".join(p.capitalize() for p in parts[1:])


def count_words(text):
    return len(re.findall(r"\b\w+\b", text, re.UNICODE))


def reading_time_minutes(text, wpm=200):
    words = count_words(text)
    return max(1, round(words / float(wpm)))
