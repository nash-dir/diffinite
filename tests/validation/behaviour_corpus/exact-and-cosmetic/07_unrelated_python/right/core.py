"""Tiny word-level Markov chain text generator."""

from __future__ import annotations

import random
import re
from collections import defaultdict
from typing import DefaultDict, List, Sequence, Tuple

TOKEN_RE = re.compile(r"[A-Za-z']+|[.!?]")
START = "<s>"


def tokenize(text: str) -> List[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


class MarkovChain:
    def __init__(self, order: int = 2, seed: int | None = None) -> None:
        if order < 1:
            raise ValueError("order must be >= 1")
        self.order = order
        self.table: DefaultDict[Tuple[str, ...], DefaultDict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self.rng = random.Random(seed)

    def train(self, text: str) -> int:
        words = tokenize(text)
        state: Tuple[str, ...] = (START,) * self.order
        added = 0
        for word in words:
            self.table[state][word] += 1
            added += 1
            if word in ".!?":
                state = (START,) * self.order
            else:
                state = state[1:] + (word,)
        return added

    def _choose(self, options: dict) -> str:
        total = sum(options.values())
        pick = self.rng.uniform(0, total)
        running = 0.0
        for word, weight in options.items():
            running += weight
            if pick <= running:
                return word
        return next(iter(options))

    def sentence(self, max_words: int = 30) -> str:
        state: Tuple[str, ...] = (START,) * self.order
        out: List[str] = []
        while len(out) < max_words:
            options = self.table.get(state)
            if not options:
                break
            word = self._choose(options)
            if word in ".!?":
                out.append(word)
                break
            out.append(word)
            state = state[1:] + (word,)
        return self._detokenize(out)

    @staticmethod
    def _detokenize(words: Sequence[str]) -> str:
        text = " ".join(words)
        text = re.sub(r" ([.!?])", r"\1", text)
        return text[:1].upper() + text[1:]

    def paragraph(self, sentences: int = 4) -> str:
        return " ".join(self.sentence() for _ in range(sentences))

    def most_likely_next(self, *context: str) -> str | None:
        key = tuple(w.lower() for w in context[-self.order:])
        if len(key) < self.order:
            key = (START,) * (self.order - len(key)) + key
        options = self.table.get(key)
        if not options:
            return None
        return max(options.items(), key=lambda kv: kv[1])[0]

    def vocabulary(self) -> List[str]:
        seen = set()
        for options in self.table.values():
            seen.update(options)
        return sorted(seen)


if __name__ == "__main__":
    import sys

    chain = MarkovChain(order=2, seed=7)
    for path in sys.argv[1:]:
        with open(path, encoding="utf-8") as fh:
            chain.train(fh.read())
    print(chain.paragraph())
