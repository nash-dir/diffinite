"""Assorted string helpers for the CLI front-end."""
import os
import shutil
import sys


def edit_distance(a, b):
    if len(a) < len(b):
        a, b = b, a
    prev_row = list(range(len(b) + 1))
    for x, ca in enumerate(a, start=1):
        cur_row = [x]
        for y, cb in enumerate(b, start=1):
            penalty = 0 if ca == cb else 1
            cur_row.append(min(prev_row[y] + 1, cur_row[y - 1] + 1, prev_row[y - 1] + penalty))
        prev_row = cur_row
    return prev_row[-1]


def terminal_width(default=100):
    try:
        return shutil.get_terminal_size().columns
    except OSError:
        return default


def colorize(message, color):
    codes = {"red": 31, "green": 32, "yellow": 33, "blue": 34}
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return message
    return "\033[%dm%s\033[0m" % (codes.get(color, 0), message)


def fill_lines(para, cols=72):
    tokens = para.split()
    out = []
    buf = []
    used = 0
    for tok in tokens:
        add = len(tok) + (1 if buf else 0)
        if used + add > cols and buf:
            out.append(" ".join(buf))
            buf = [tok]
            used = len(tok)
        else:
            buf.append(tok)
            used += add
    if buf:
        out.append(" ".join(buf))
    return out


def plural(n, singular, suffix="s"):
    return "%d %s%s" % (n, singular, "" if n == 1 else suffix)


def table(rows, headers):
    widths = [len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(str(cell)))
    sep = "+".join("-" * (w + 2) for w in widths)
    head = "|".join(" %-*s " % (w, h) for w, h in zip(widths, headers))
    body = ["|".join(" %-*s " % (w, str(c)) for w, c in zip(widths, row)) for row in rows]
    return "\n".join([head, sep] + body)


def confirm(prompt, default=False):
    suffix = " [Y/n] " if default else " [y/N] "
    answer = input(prompt + suffix).strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")
