"""Readability and frequency statistics for plain-text documents."""

import re

VOWELS = "aeiouy"
SENTENCE_END = re.compile(r"[.!?]+")
WORD = re.compile(r"[A-Za-z']+")


def count_syllables(word):
    word = word.lower().strip("'")
    if not word:
        return 0
    count = 0
    prev_vowel = False
    i = 0
    while i < len(word):
        is_vowel = word[i] in VOWELS
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
        i += 1
    if word.endswith("e") and count > 1 and not word.endswith("le"):
        count -= 1
    return max(count, 1)


def split_sentences(text):
    pieces = SENTENCE_END.split(text)
    sentences = []
    idx = 0
    while idx < len(pieces):
        piece = pieces[idx].strip()
        if piece:
            sentences.append(piece)
        idx += 1
    return sentences


def word_frequencies(text, stopwords=()):
    freq = {}
    stop = set(w.lower() for w in stopwords)
    matches = list(WORD.finditer(text))
    j = 0
    while j < len(matches):
        w = matches[j].group(0).lower()
        j += 1
        if w in stop or len(w) < 2:
            continue
        freq[w] = freq.get(w, 0) + 1
    return freq


def top_words(freq, n=10):
    ranked = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))
    result = []
    i = 0
    while i < n and i < len(ranked):
        result.append(ranked[i])
        i += 1
    return result


def flesch_reading_ease(text):
    sentences = split_sentences(text)
    words = WORD.findall(text)
    if not sentences or not words:
        return 0.0
    syllables = 0
    k = 0
    while k < len(words):
        syllables += count_syllables(words[k])
        k += 1
    wps = len(words) / len(sentences)
    spw = syllables / len(words)
    return round(206.835 - 1.015 * wps - 84.6 * spw, 2)


def longest_run(lines, predicate):
    best = 0
    current = 0
    pos = 0
    while pos < len(lines):
        if predicate(lines[pos]):
            current += 1
            if current > best:
                best = current
        else:
            current = 0
        pos += 1
    return best


def paragraph_lengths(text):
    lengths = []
    words_in_para = 0
    lines = text.splitlines()
    n = 0
    while n < len(lines):
        line = lines[n]
        n += 1
        if line.strip() == "":
            if words_in_para:
                lengths.append(words_in_para)
            words_in_para = 0
            continue
        words_in_para += len(WORD.findall(line))
    if words_in_para:
        lengths.append(words_in_para)
    return lengths


def summarize(text, stopwords=()):
    freq = word_frequencies(text, stopwords)
    paras = paragraph_lengths(text)
    return {
        "sentences": len(split_sentences(text)),
        "words": sum(freq.values()),
        "unique_words": len(freq),
        "paragraphs": len(paras),
        "avg_paragraph": round(sum(paras) / len(paras), 1) if paras else 0.0,
        "flesch": flesch_reading_ease(text),
        "top": top_words(freq, 5),
        "longest_blank_run": longest_run(text.splitlines(), lambda l: not l.strip()),
    }
