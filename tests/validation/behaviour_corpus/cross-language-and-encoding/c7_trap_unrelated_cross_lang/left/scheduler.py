"""Minimal cron-expression parser and next-run calculator."""

from datetime import datetime, timedelta

FIELDS = [
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day", 1, 31),
    ("month", 1, 12),
    ("weekday", 0, 6),
]


def parse_field(expr, low, high):
    values = set()
    for part in expr.split(","):
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            step = int(step_text)
            if step <= 0:
                raise ValueError("step must be positive")
        if part == "*":
            start, end = low, high
        elif "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(part)
        if start < low or end > high or start > end:
            raise ValueError("value out of range: %s" % part)
        values.update(range(start, end + 1, step))
    return values


def parse_cron(expression):
    parts = expression.split()
    if len(parts) != len(FIELDS):
        raise ValueError("cron expression needs 5 fields")
    return {
        name: parse_field(text, low, high)
        for (name, low, high), text in zip(FIELDS, parts)
    }


def matches(schedule, moment):
    return (
        moment.minute in schedule["minute"]
        and moment.hour in schedule["hour"]
        and moment.day in schedule["day"]
        and moment.month in schedule["month"]
        and (moment.weekday() + 1) % 7 in schedule["weekday"]
    )


def next_run(expression, after, horizon_days=366):
    schedule = parse_cron(expression)
    moment = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    limit = after + timedelta(days=horizon_days)
    while moment <= limit:
        if moment.month not in schedule["month"]:
            moment = (moment.replace(day=1, hour=0, minute=0) + timedelta(days=32)).replace(day=1)
            continue
        if matches(schedule, moment):
            return moment
        moment += timedelta(minutes=1)
    return None


def upcoming(expression, start, count=5):
    runs = []
    cursor = start
    for _ in range(count):
        nxt = next_run(expression, cursor)
        if nxt is None:
            break
        runs.append(nxt)
        cursor = nxt
    return runs


if __name__ == "__main__":
    for run in upcoming("*/15 9-17 * * 1-5", datetime(2026, 11, 2, 8, 50)):
        print(run.isoformat())
