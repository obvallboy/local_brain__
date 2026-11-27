"""Learning from normal conversation.

"my brother's name is leo"            -> drawer 1: subject "brother", "Your brother's name is leo."
"we just saw a blue bike at the library" -> episode log: place "Library", details as told
Extraction is rules only, so the same sentence is always filed the same way.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PHRASE_FLIPS = [
    (r"\bi was\b", "you were"), (r"\bi am\b", "you are"), (r"\bi'm\b", "you're"), (r"\bi've\b", "you've"),
    (r"\bi'll\b", "you'll"), (r"\bi'd\b", "you'd"),
]
_WORD_FLIPS = {"my": "your", "mine": "yours", "i": "you", "me": "you", "myself": "yourself"}

_VERBS = r"(is|are|was|were|lives|works|has|likes|loves|hates|plays|drives|goes|studies)"


def second_person(text: str) -> str:
    """Rewrite something the owner said about themselves so it reads as "you"."""
    t = text.strip().rstrip(".!")
    for pattern, repl in _PHRASE_FLIPS:
        t = re.sub(pattern, repl, t)
    t = re.sub(r"\b(my|mine|i|me|myself)\b", lambda m: _WORD_FLIPS[m.group(1)], t)
    return t[0].upper() + t[1:] + "."


@dataclass(frozen=True)
class TaughtFact:
    subject: str
    fact: str


_FILLER = re.compile(
    r"^(fyi|btw|by the way|just so you know|for the record|note that|remember that|remember:|"
    r"keep in mind( that)?|don't forget( that)?|dont forget( that)?|heads up)[,:]?\s+"
)


def extract_fact(text: str) -> TaughtFact | None:
    t = " ".join(text.strip().lower().replace("’", "'").split()).rstrip(".!")
    t = _FILLER.sub("", t)
    if m := re.match(r"^(?!(?:this|that|it|he|she|they|there|here|what|who)\b)([\w']+) is my ((?:[\w']+ ){0,2}[\w']+)$", t):
        name, relation = m.group(1), m.group(2)
        return TaughtFact(f"{relation} {name}", f"{name.title()} is your {relation}.")
    if m := re.match(r"^my ([\w' ]+?)(?:'s)? name is (.+)$", t):
        return TaughtFact(m.group(1), f"Your {m.group(1)}'s name is {m.group(2)}.")
    if m := re.match(r"^my ([\w' ]+?) is (?:named|called) (.+)$", t):
        return TaughtFact(m.group(1), f"Your {m.group(1)} is named {m.group(2)}.")
    if m := re.match(rf"^my ((?:[\w']+ ){{0,2}}[\w']+) {_VERBS}\b", t):
        return TaughtFact(m.group(1), second_person(t))
    if re.match(r"^i (really )?(like|love|hate|dislike|enjoy|prefer)\b", t):
        return TaughtFact("likes", second_person(t))
    if m := re.match(r"^i (work|live|was born|grew up|study|go to|am from|'m from)\b", t):
        key = {"was born": "born", "grew up": "grew up", "go to": "go to", "am from": "from", "'m from": "from"}
        return TaughtFact(key.get(m.group(1), m.group(1)), second_person(t))
    if m := re.match(r"^i (drive|own|play|speak|ride)\b", t):
        return TaughtFact(m.group(1), second_person(t))
    if m := re.match(r"^(?:i'm|i am) (allergic to|from) (.+)$", t):
        return TaughtFact(m.group(1).split()[0], second_person(t))
    if m := re.match(r"^(?:i'm|i am) (\d+)(?: years old)?$", t):
        return TaughtFact("age, how old", f"You are {m.group(1)} years old.")  # "how old am i" finds it
    if re.match(r"^(i'm|i am) (a|an) ", t):
        return TaughtFact("who you are", second_person(t))
    return None


@dataclass(frozen=True)
class TaughtEvent:
    place: str
    activity: str
    details: str
    people: str


_STOP = r"(?:\b(?:and|with|this|today|tonight|yesterday|earlier|just|for|to|at)\b|[,.!]|$)"
_ACTIVITIES = [
    (r"\bdinner\b", "dinner"), (r"\blunch\b", "lunch"), (r"\bbreakfast\b", "breakfast"),
    (r"\bmovie|film\b", "watching a movie"), (r"\bwalk", "walking"), (r"\bmarket|shop|store|mall\b", "shopping"),
    (r"\bbeach|swim", "at the beach"), (r"\bplay", "playing"), (r"\bdrive|drove\b", "driving"),
]


def extract_event(text: str) -> TaughtEvent:
    raw = " ".join(text.strip().split())
    t = raw.lower().replace("’", "'")
    place = "here"
    if m := re.search(rf"\b(?:at|to|in) (?:the )?([\w' ]+?){_STOP}", t):
        place = m.group(1).strip().title() or place
    people = ""
    if m := re.search(rf"\bwith ([\w' ]+?){_STOP}", t):
        people = m.group(1).strip().title()
    activity = next((name for pattern, name in _ACTIVITIES if re.search(pattern, t)), "together")
    details = raw[0].upper() + raw[1:]
    if not details.endswith((".", "!", "?")):
        details += "."
    return TaughtEvent(place, activity, details, people)
