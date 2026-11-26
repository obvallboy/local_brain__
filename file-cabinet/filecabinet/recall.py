"""Recall by cue (context reinstatement).

1. Look directly for the memory in the episode log.
2. If it is not there, ask "Where were we?", rebuild that scene from
   everything logged at the same place and time, and look again.
3. A memory only counts if it is found in the log. Nothing is generated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .similarity import Matcher, tokens
from .store import Episode, Store

COLORS = {
    "red", "orange", "yellow", "green", "blue", "purple", "pink", "brown", "black", "white",
    "gray", "grey", "silver", "gold", "beige", "tan", "teal", "navy", "maroon",
}

# Words that describe the act of remembering rather than the thing remembered.
META = set(tokens(
    "remember recall forgot earlier yesterday today morning tonight night last time week ago before "
    "other day that saw see seen spotted noticed went go did do thing stuff something anything again "
    "remind tell kind"
))

ATTRIBUTES = {
    "color": re.compile(r"\b(colou?r)\b", re.I),
    "place": re.compile(r"\bwhere\b", re.I),
    "time": re.compile(r"\b(when|what time)\b", re.I),
    "who": re.compile(r"\b(who|with whom)\b", re.I),
}
ATTRIBUTE_WORDS = set(tokens("color colour where when time who whom"))


@dataclass
class RecallResult:
    found: bool
    text: str
    evidence: list[str] = field(default_factory=list)
    cues: list[str] = field(default_factory=list)


def time_window(question: str, now: datetime) -> tuple[datetime, datetime] | None:
    q = question.lower()
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if "last night" in q:
        return day - timedelta(hours=7), day + timedelta(hours=6)
    if "yesterday" in q:
        return day - timedelta(days=1), day
    if any(w in q for w in ("earlier", "today", "this morning", "tonight", "just now")):
        return day, day + timedelta(days=1)
    if "last week" in q:
        return day - timedelta(days=7), day + timedelta(days=1)
    return None


def detect_attribute(question: str) -> str | None:
    for name, pattern in ATTRIBUTES.items():
        if pattern.search(question):
            return name
    return None


def attribute_in(episode: Episode, attribute: str | None) -> str | None:
    """Return the words that answer the attribute, if this episode holds them."""
    if attribute is None:
        return episode.details
    if attribute == "color":
        words = set(re.findall(r"[a-z]+", episode.details.lower()))
        return episode.details if words & COLORS else None
    if attribute == "place":
        return f"at {episode.place}"
    if attribute == "time":
        return f"on {episode.ts.strftime('%A')} at {_clock(episode.ts)}"
    if attribute == "who":
        return f"with {episode.people}" if episode.people else None
    return None




def _clock(dt: datetime) -> str:
    """12-hour time without a leading zero, portable to Windows."""
    return f"{int(dt.strftime('%I'))}:{dt.strftime('%M %p')}"


def _context(e: Episode) -> str:
    return f"{e.place}, {e.activity}, {e.ts.strftime('%a')} {_clock(e.ts)}"


def recall(question: str, store: Store, now: datetime, matcher: Matcher | None = None) -> RecallResult:
    matcher = matcher or Matcher()

    def _overlap(terms: set[str], episode: Episode) -> float:
        return matcher.overlap(terms, episode.text())

    window = time_window(question, now)
    episodes = store.episodes(*window) if window else store.episodes()
    attribute = detect_attribute(question)
    terms = set(tokens(question)) - META - ATTRIBUTE_WORDS

    # Step 1: look directly.
    ranked = sorted(
        (e for e in episodes if _overlap(terms, e) > 0),
        key=lambda e: (-_overlap(terms, e), -e.ts.timestamp(), -e.id),
    )
    for e in ranked:
        if _overlap(terms, e) >= 0.5 and (answer := attribute_in(e, attribute)):
            return RecallResult(True, _phrase(answer, e, attribute), [f"episode #{e.id}: {e.details} ({_context(e)})"])

    # Step 2: cue questions. Put myself back where the thing was and look for the missing detail.
    # Only a strong match (at least half the words) can anchor a scene; one shared word is not a memory.
    cues = ["Where were we?"]
    strong = [e for e in ranked if _overlap(terms, e) >= 0.5]
    seen_scenes = set()
    for anchor in strong:
        key = (anchor.place.lower(), anchor.ts.date())
        if key in seen_scenes or attribute is None:
            continue
        seen_scenes.add(key)
        cues.append(f"We were at {anchor.place} ({anchor.activity}). What else was there?")
        for e in sorted(store.scene(anchor), key=lambda x: x.ts):
            if answer := attribute_in(e, attribute):
                evidence = [f"episode #{anchor.id}: {anchor.details} ({_context(anchor)})"]
                if e.id != anchor.id:
                    evidence.append(f"episode #{e.id}: {e.details} ({_context(e)})")
                return RecallResult(True, _phrase(answer, e, attribute), evidence, cues)

    # Nothing found in the log: say so, never fill the gap.
    thing = " ".join(sorted(terms)) or "that"
    if strong:
        a = strong[0]
        detail = {"color": "its color", "place": "where it was", "time": "when it was", "who": "who was there"}.get(attribute, "more than that")
        return RecallResult(
            False,
            f"I remember {a.details[0].lower() + a.details[1:].rstrip('.')} ({_context(a)}), but I don't remember {detail}.",
            [f"episode #{a.id}: {a.details}"],
            cues,
        )
    places = sorted({e.place for e in episodes})
    where = f" I went back through where we were ({', '.join(places)}), and it isn't there." if places else ""
    return RecallResult(False, f"I don't remember that. I looked for \"{thing}\".{where}", [], cues)


def _phrase(answer: str, e: Episode, attribute: str | None) -> str:
    context = _context(e)
    if attribute in ("place", "time", "who"):
        return f"{answer[0].upper() + answer[1:]}. ({e.details.rstrip('.')}; {context})"
    return f"{answer.rstrip('.')}. ({context})"
