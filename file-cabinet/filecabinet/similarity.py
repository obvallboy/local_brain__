"""Small, dependency-free text matching used to find files by similarity.

An optional embedder adds matching by meaning: a word counts as present if a
word in the text means the same thing (similarity at least 0.85).
"""

from __future__ import annotations

import math
import re
from collections import Counter

STOPWORDS = frozenset(
    """a an the is are was were be been being am i im i'm you we he she it they me my
    your our his her its their this that these those of in on at to for from with by
    about as and or but if then so do does did done have has had what which who whom
    whose when where why how can could would should will shall may might must not no
    yes there here just also very really any some all each every than too into out up
    down over under again once us them him what's who's where's how's""".split()
)

# Irregular past tenses and close verb synonyms, so "ate" matches "eat" and "spotted" matches "saw".
LEMMAS = {
    "ate": "eat", "eaten": "eat", "dined": "eat", "dine": "eat", "saw": "see", "seen": "see",
    "spotted": "see", "spot": "see", "noticed": "see", "notice": "see", "went": "go", "gone": "go",
    "found": "find", "bought": "buy", "met": "meet", "took": "take", "told": "tell", "said": "say",
    "made": "make", "drove": "drive", "rode": "ride", "came": "come", "got": "get", "ran": "run",
    "sat": "sit", "gave": "give", "won": "win", "felt": "feel", "thought": "think", "brought": "bring",
    "caught": "catch", "taught": "teach", "heard": "hear", "kept": "keep", "slept": "sleep",
    "wore": "wear", "wrote": "write", "spoke": "speak", "stood": "stand", "threw": "throw",
    "flew": "fly", "drew": "draw", "drank": "drink", "swam": "swim", "sang": "sing", "joined": "join",
    "watched": "watch", "talked": "talk", "called": "call", "named": "name",
}

_WORD = re.compile(r"[a-z0-9']+")


def stem(word: str) -> str:
    """A tiny suffix stripper so 'loading', 'loaded' and 'loads' match."""
    for suffix in ("ing", "ed", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix) and not word.endswith("ss"):
            return word[: -len(suffix)]
    return word


def tokens(text: str) -> list[str]:
    out = []
    for raw in _WORD.findall(text.lower().replace("’", "'")):
        word = raw.strip("'")
        if word.endswith("'s"):
            word = word[:-2]
        if not word or word in STOPWORDS:
            continue
        out.append(LEMMAS.get(word) or stem(word))
    return out


def cosine(a: list[str], b: list[str]) -> float:
    ca, cb = Counter(a), Counter(b)
    if not ca or not cb:
        return 0.0
    dot = sum(ca[t] * cb[t] for t in ca.keys() & cb.keys())
    norm = math.sqrt(sum(v * v for v in ca.values())) * math.sqrt(sum(v * v for v in cb.values()))
    return dot / norm


def similarity(text_a: str, text_b: str) -> float:
    return cosine(tokens(text_a), tokens(text_b))


class Matcher:
    """Word matching by exact form, and by meaning when an embedder is available."""

    def __init__(self, embedder=None, threshold: float = 0.85):
        self.embedder = embedder
        self.threshold = threshold

    def find(self, term: str, words) -> str | None:
        """The word in `words` that matches `term`, if any."""
        if term in words:
            return term
        if self.embedder is None or len(term) < 3:
            return None
        best = max(((self.embedder.similarity(term, w), w) for w in words if len(w) >= 3), default=(0.0, None))
        return best[1] if best[0] >= self.threshold else None

    def overlap(self, terms: set[str], text: str) -> float:
        if not terms:
            return 0.0
        words = set(tokens(text))
        return sum(self.find(t, words) is not None for t in terms) / len(terms)

    def similarity(self, query: str, reference: str) -> float:
        """Cosine similarity after mapping query words onto same-meaning reference words."""
        ref = tokens(reference)
        ref_words = set(ref)
        aligned = [self.find(t, ref_words) or t for t in tokens(query)]
        return cosine(aligned, ref)
