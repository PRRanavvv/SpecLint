from __future__ import annotations

import hashlib
import re
from collections import Counter


STOPWORDS = {
    "a",
    "able",
    "about",
    "after",
    "all",
    "also",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "do",
    "for",
    "from",
    "has",
    "have",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "should",
    "that",
    "the",
    "their",
    "then",
    "this",
    "to",
    "when",
    "where",
    "which",
    "with",
}


def stable_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def split_sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text.strip())
    if not compact:
        return []
    pieces = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", compact)
    return [piece.strip() for piece in pieces if piece.strip()]


def tokenize(text: str) -> list[str]:
    return [
        word
        for word in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{1,}", text.lower())
        if word not in STOPWORDS
    ]


def contains_any(text: str, terms: set[str]) -> bool:
    tokens = set(tokenize(text))
    return bool(tokens & terms)


def compact_quote(text: str, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", text.strip())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}..."


def top_terms(text: str, count: int = 8) -> list[str]:
    frequencies = Counter(tokenize(text))
    return [term for term, _ in frequencies.most_common(count)]

