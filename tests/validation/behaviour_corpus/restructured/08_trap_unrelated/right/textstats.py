"""Document analyser: counts, n-grams and a Gunning-fog style index.

Written independently; shares only the problem domain with other text tools.
"""

from __future__ import annotations

import string
from collections import Counter
from typing import Iterable, Iterator


_PUNCT = set(string.punctuation) - {"'", "-"}
_TERMINATORS = {".", "?", "!"}


def tokens(text: str) -> Iterator[str]:
    buf: list[str] = []
    for ch in text:
        if ch.isalpha() or ch in "'-":
            buf.append(ch.lower())
        elif buf:
            yield "".join(buf).strip("'-")
            buf.clear()
    if buf:
        yield "".join(buf).strip("'-")


def sentence_count(text: str) -> int:
    n = 0
    in_terminator = False
    for ch in text:
        if ch in _TERMINATORS:
            if not in_terminator:
                n += 1
            in_terminator = True
        elif not ch.isspace():
            in_terminator = False
    tail = text.rstrip()
    if tail and tail[-1] not in _TERMINATORS:
        n += 1
    return n


def vowel_groups(word: str) -> int:
    groups = 0
    last = ""
    for ch in word:
        kind = "v" if ch in "aeiou" else "c"
        if kind == "v" and last != "v":
            groups += 1
        last = kind
    return groups or 1


class Document:
    def __init__(self, text: str, ignore: Iterable[str] = ()) -> None:
        self.text = text
        self.ignore = frozenset(w.lower() for w in ignore)
        self._words = [t for t in tokens(text) if t]

    @property
    def words(self) -> list[str]:
        return self._words

    def counts(self) -> Counter:
        return Counter(w for w in self._words if w not in self.ignore)

    def ngrams(self, n: int = 2) -> Counter:
        seq = [w for w in self._words if w not in self.ignore]
        return Counter(tuple(seq[i:i + n]) for i in range(len(seq) - n + 1))

    def complex_words(self) -> int:
        return sum(1 for w in self._words if vowel_groups(w) >= 3 and not w.endswith(("es", "ed")))

    def fog_index(self) -> float:
        s = max(sentence_count(self.text), 1)
        w = max(len(self._words), 1)
        return round(0.4 * ((w / s) + 100.0 * self.complex_words() / w), 2)

    def lexical_density(self) -> float:
        if not self._words:
            return 0.0
        return round(len(set(self._words)) / len(self._words), 3)

    def blocks(self) -> list[int]:
        chunks = [c for c in self.text.split("\n\n") if c.strip()]
        return [sum(1 for _ in tokens(c)) for c in chunks]

    def report(self, top: int = 5) -> dict:
        blk = self.blocks()
        return {
            "tokens": len(self._words),
            "types": len(set(self._words)),
            "sentences": sentence_count(self.text),
            "blocks": len(blk),
            "mean_block": (sum(blk) / len(blk)) if blk else 0.0,
            "fog": self.fog_index(),
            "density": self.lexical_density(),
            "common": self.counts().most_common(top),
            "bigrams": self.ngrams(2).most_common(top),
        }
