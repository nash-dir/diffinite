"""Text utilities used by the reporting service."""
import re
import unicodedata

_WS = re.compile(r"\s+")
_SLUG_BAD = re.compile(r"[^a-z0-9]+")


def normalize_text(text):
    text = unicodedata.normalize("NFKC", text)
    text = _WS.sub(" ", text)
    return text.strip()


def slugify(title, max_length=48):
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = _SLUG_BAD.sub("-", ascii_title.lower()).strip("-")
    if len(slug) > max_length:
        slug = slug[:max_length].rsplit("-", 1)[0]
    return slug or "untitled"


def wrap_paragraph(paragraph, width=72):
    words = paragraph.split()
    lines = []
    current = []
    length = 0
    for word in words:
        extra = len(word) + (1 if current else 0)
        if length + extra > width and current:
            lines.append(" ".join(current))
            current = [word]
            length = len(word)
        else:
            current.append(word)
            length += extra
    if current:
        lines.append(" ".join(current))
    return lines


def levenshtein(source, target):
    if len(source) < len(target):
        source, target = target, source
    previous = list(range(len(target) + 1))
    for i, sc in enumerate(source, start=1):
        row = [i]
        for j, tc in enumerate(target, start=1):
            cost = 0 if sc == tc else 1
            row.append(min(previous[j] + 1, row[j - 1] + 1, previous[j - 1] + cost))
        previous = row
    return previous[-1]


def word_frequencies(text, stopwords=frozenset()):
    counts = {}
    for token in re.findall(r"[a-zA-Z']+", text.lower()):
        if token in stopwords:
            continue
        counts[token] = counts.get(token, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))


def truncate(text, limit=80, ellipsis="..."):
    if len(text) <= limit:
        return text
    cut = text[: limit - len(ellipsis)]
    space = cut.rfind(" ")
    if space > limit // 2:
        cut = cut[:space]
    return cut + ellipsis
