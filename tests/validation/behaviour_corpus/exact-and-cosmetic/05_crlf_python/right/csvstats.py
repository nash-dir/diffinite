"""Streaming descriptive statistics over CSV columns."""

import csv
import math
import sys
from collections import Counter


class RunningStats:
    """Welford's online algorithm for mean and variance."""

    def __init__(self):
        self.n = 0
        self.mean = 0.0
        self._m2 = 0.0
        self.minimum = math.inf
        self.maximum = -math.inf

    def push(self, x):
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        self._m2 += delta * (x - self.mean)
        if x < self.minimum:
            self.minimum = x
        if x > self.maximum:
            self.maximum = x

    @property
    def variance(self):
        if self.n < 2:
            return 0.0
        return self._m2 / (self.n - 1)

    @property
    def stdev(self):
        return math.sqrt(self.variance)

    def as_dict(self):
        return {
            "count": self.n,
            "mean": round(self.mean, 6),
            "stdev": round(self.stdev, 6),
            "min": self.minimum if self.n else None,
            "max": self.maximum if self.n else None,
        }


def try_float(text):
    text = text.strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def profile(path, delimiter=",", max_categories=10):
    numeric = {}
    categorical = {}
    missing = Counter()
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)
        for row in reader:
            for col, raw in row.items():
                if raw is None or raw.strip() == "":
                    missing[col] += 1
                    continue
                value = try_float(raw)
                if value is not None and col not in categorical:
                    numeric.setdefault(col, RunningStats()).push(value)
                else:
                    numeric.pop(col, None)
                    categorical.setdefault(col, Counter())[raw.strip()] += 1
    report = {}
    for col, stats in numeric.items():
        report[col] = {"type": "numeric", **stats.as_dict(), "missing": missing[col]}
    for col, counts in categorical.items():
        report[col] = {
            "type": "categorical",
            "distinct": len(counts),
            "top": counts.most_common(max_categories),
            "missing": missing[col],
        }
    return report


def render(report, out=sys.stdout):
    for col in sorted(report):
        info = report[col]
        out.write(f"== {col} ({info['type']}) ==\n")
        if info["type"] == "numeric":
            out.write(
                f"  n={info['count']} mean={info['mean']} sd={info['stdev']}"
                f" range=[{info['min']}, {info['max']}]\n"
            )
        else:
            out.write(f"  distinct={info['distinct']}\n")
            for value, count in info["top"]:
                out.write(f"    {value!r}: {count}\n")
        out.write(f"  missing={info['missing']}\n")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        sys.stderr.write("usage: csvstats FILE [DELIM]\n")
        return 2
    delim = argv[1] if len(argv) > 1 else ","
    render(profile(argv[0], delimiter=delim))
    return 0


if __name__ == "__main__":
    sys.exit(main())
