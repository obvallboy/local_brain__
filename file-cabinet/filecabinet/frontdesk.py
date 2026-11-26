"""The front desk: decides what kind of message this is and which drawers to open.

Three tiers, in order:
  1. Safety rules (crisis and deep emotion). Always checked first; nothing can overrule them.
  2. Clear patterns (explicit recall, teaching a fact, telling an event).
  3. Everything else: the local model classifies the message into a fixed set of
     kinds (forced JSON, temperature 0). Without a model, simpler rules are used.
The model may raise a message to deep emotion or flag risk; it can never lower
what the safety rules decided.
"""

from __future__ import annotations

import re

from .answer import Route
from .devices import DEVICE_QUESTION

# ---- normalization -------------------------------------------------------
_SLANG = [
    (r"\bwhats\b", "what's"), (r"\bwhos\b", "who's"), (r"\bwheres\b", "where's"), (r"\bhows\b", "how's"),
    (r"\bu\b", "you"), (r"\bur\b", "your"), (r"\bim\b", "i'm"), (r"\bive\b", "i've"), (r"\bdont\b", "don't"),
    (r"\bcant\b", "can't"), (r"\bwont\b", "won't"), (r"\bisnt\b", "isn't"), (r"\barent\b", "aren't"),
    (r"\bdidnt\b", "didn't"), (r"\bdoesnt\b", "doesn't"), (r"\bwasnt\b", "wasn't"), (r"\bthats\b", "that's"),
    (r"\bsisters\b(?= name)", "sister's"), (r"\bbrothers\b(?= name)", "brother's"),
]


def normalize(text: str) -> str:
    t = " ".join(text.strip().lower().replace("’", "'").split())
    for pattern, repl in _SLANG:
        t = re.sub(pattern, repl, t)
    return t


# ---- tier 1: safety ------------------------------------------------------
_FAMILY = (r"(friend|best friend|mom|mother|dad|father|brother|sister|son|daughter|wife|husband|partner|"
           r"grandma|grandpa|grandmother|grandfather|aunt|uncle|cousin|dog|cat|pet|baby|job)")

CRISIS = re.compile(
    r"\b(suicid\w*|kill(ing)? myself|end(ing)? my life|end(ing)? it all|hurt(ing)? myself|harm(ing)? myself|"
    r"self[- ]harm|want to die|wanna die|no reason to live|better off without me|"
    r"(don't|do not) want to (be here|live|wake up)|"
    r"can't (keep going|go on)|(don't|do not) know (if|how) i can (keep going|go on))\b",
    re.I,
)
DEEP = re.compile(
    r"\b(died|death|passed away|passed (on|last|this|yesterday|recently)|funeral|grie(f|ving|ve)|divorc\w*|"
    r"broke up|break ?up|fight|fought|betray\w*|depress\w*|lonely|faith|god|pray\w*|scared|afraid|anxious|"
    r"anxiety|hopeless|worthless|pointless|abus\w*|crying|cried|heartbroken|bad news|"
    r"(isn't|is not|not|no longer) with us( anymore)?|nobody (gets|understands|cares about) me|"
    r"(been|feeling|feel) (really |so |kinda |pretty )?down|"
    rf"lost (my|a|our) {_FAMILY}|losing (my|a|our) {_FAMILY}|miss (him|her|them|my {_FAMILY}))\b",
    re.I,
)

# ---- tier 2: clear patterns -----------------------------------------------
QUESTION = re.compile(
    r"\?\s*$|^(what|what's|who|who's|whom|when|where|where's|why|how|how's|which|is|are|was|were|do|does|did|"
    r"can|could|will|would|should|have|has|remind me|tell me)\b",
    re.I,
)
EXPLICIT_RECALL = re.compile(r"\b(remember|recall|forgot|forget)\b", re.I)
PAST_SHARED = re.compile(
    r"\b(earlier|yesterday|last night|last time|the other day|that time|did we|were we|we saw|we went|we ate|"
    r"we did|we had|we found|we talked|we watched|with us)\b",
    re.I,
)
TEACH = re.compile(
    r"^(my (?:[\w']+ ){0,2}[\w']+ (is|are|was|were|lives|works|has|likes|loves|hates|plays|drives|goes|studies)\b|"
    r"my (?:[\w']+ ){0,2}[\w']+'s name is\b|"
    r"i (really )?(like|love|hate|dislike|enjoy|prefer)\b|"
    r"i (work|live|was born|grew up|study|go to|am from|'m from)\b|i'm (a|an) |i am (a|an) )",
    re.I,
)
EVENT = re.compile(
    r"^((we|i) (just )?(saw|went|had|watched|ate|found|met|got back|came back|visited|played|walked|bought|"
    r"heard|tried|made|talked)\b|just (had|saw|got|went|watched|ate|found|met|finished|got back)\b|"
    r"(went|saw|had|watched|ate|found|met|visited) )",
    re.I,
)

# ---- tier 3 without a model ----------------------------------------------
FEELING = re.compile(
    r"\b(feel\w*|sad|upset|angry|mad|worried|stress\w*|hurt|happy|excited|nervous|proud|glad|overwhelmed|bummed)\b",
    re.I,
)
TASK = re.compile(
    r"\b(fix|troubleshoot\w*|diagnos\w*|debug\w*|not working|isn't working|won't|can't connect|cannot connect|"
    r"no internet|is down|broken|keeps dropping|dropping|cutting out|cuts out|won't load|not loading|"
    r"nothing (will )?(load|works|opens)|slow|blinking)\b",
    re.I,
)
OPINION = re.compile(
    r"\b(funny|pretty|cute|cool|ugly|nice|beautiful|good[- ]looking|awesome|boring|slaps|overrated|"
    r"do you like|you like|do you love|favou?rite|prefer|your take|do you think|would you say|better)\b",
    re.I,
)
PERSONAL = re.compile(r"\b(my|mine|i|me|i'm|myself|we|us)\b", re.I)
SHARED_HINT = re.compile(r"\b(we|us|our|that|those|again)\b", re.I)  # plain past tense is not a shared memory
NETWORK_WORDS = re.compile(r"\b(wi-?fi|internet|network|router|modem|dns|ethernet|connect\w*|load|browser|online)\b", re.I)
GENERAL_OUR = re.compile(r"\bour (solar system|planet|world|galaxy|universe|sun|moon|country|species)\b", re.I)

KINDS = ["opinion", "fact", "recall", "task", "emotional", "chat", "teach", "event"]
CLASSIFIER_SCHEMA = {
    "type": "object",
    "properties": {"kind": {"type": "string", "enum": KINDS}, "self_harm_risk": {"type": "boolean"}},
    "required": ["kind", "self_harm_risk"],
}
CLASSIFIER_SYSTEM = """Classify the user's message for a personal assistant. Kinds:
opinion: asks what the assistant thinks of or likes about something ("is blue a nice color", "you like dogs or cats?")
fact: asks for a fact about the user or the world ("what's my sister's name", "how far is the moon")
recall: asks about something that happened before that the user and assistant shared ("what color was that car at the park")
task: describes a technical problem to fix ("my wifi keeps cutting out", "nothing will load")
emotional: shares feelings, stress, loss, or hard news ("i've been down lately", "my grandma isn't with us anymore")
chat: greetings, thanks, small talk ("hey", "thanks", "lol nice")
teach: the user states a lasting fact about themselves or their life ("my brother lives in austin")
event: the user tells something that just happened or that they did ("we just saw a red car")
Set self_harm_risk to true only if the message suggests the user may hurt themselves or not want to live."""

DRAWERS = {
    "opinion": ("drawer1",),
    "recall": ("drawer2:recall",),
    "task": ("temp", "drawer2"),
    "chat": ("drawer2",),
    "teach": ("drawer1:file",),
    "event": ("episode log:file",),
    "emotional": ("drawer3",),
    "devices": ("temp:devices",),
}


class FrontDesk:
    def __init__(self, model=None, devices: bool = False):
        self.model = model
        self.devices = devices  # the host app can show what is plugged in

    def route(self, text: str, known=None) -> Route:
        """known: optional check "does drawer 1 already hold the answer?" A question it
        answers skips the model entirely (drawer 1 first, instantly)."""
        t = normalize(text)
        is_question = bool(QUESTION.search(t))
        recall = bool(EXPLICIT_RECALL.search(t) or (is_question and PAST_SHARED.search(t)))

        # Tier 1: safety. Never overruled.
        if CRISIS.search(t):
            return Route("emotional", "deep", DRAWERS["emotional"], "it may be about self-harm", recall=recall, crisis=True)
        if DEEP.search(t):
            return Route("emotional", "deep", DRAWERS["emotional"], "it touches something heavy", recall=recall)

        # Tier 2: clear patterns.
        if recall:
            return Route("recall", "surface", DRAWERS["recall"], "it asks about something we shared", recall=True)
        if not is_question and TEACH.search(t):
            return Route("teach", "surface", DRAWERS["teach"], "it tells me a lasting fact")
        if not is_question and EVENT.search(t):
            return Route("event", "surface", DRAWERS["event"], "it tells me something that happened")
        if self.devices and DEVICE_QUESTION.search(t):
            return Route("devices", "surface", DRAWERS["devices"], "it asks about the hardware attached right now")

        # Drawer 1 first: if a question's answer is already filed, no model call is needed.
        if is_question and known is not None and known(text):
            return Route("fact", "surface", ("drawer1",), "drawer 1 already has the answer")

        # Tier 3: the model, or simple rules without one.
        kind, risk, how = self._classify(t, is_question)
        if risk:
            return Route("emotional", "deep", DRAWERS["emotional"], f"{how} flagged possible self-harm", crisis=True)
        if kind == "emotional":
            return Route("emotional", "deep", DRAWERS["emotional"], f"{how}: it is about feelings (unclear depth is treated as deep)")
        if kind == "fact":
            if PERSONAL.search(t) and not GENERAL_OUR.search(t):
                return Route("fact", "surface", ("drawer1",), f"{how}: it asks a personal fact")
            return Route("fact", "surface", ("drawer1", "drawer2"), f"{how}: it asks a general fact")
        return Route(kind, "surface", DRAWERS[kind], f"{how}: {kind}", recall=kind == "recall")

    def _classify(self, t: str, is_question: bool) -> tuple[str, bool, str]:
        # Rules first (as the design says); the model only decides what the rules cannot.
        kind = self._rules(t, is_question)
        if kind not in ("fact", "chat") or self.model is None or not hasattr(self.model, "ask_json"):
            return kind, False, "rules"
        data = self.model.ask_json(CLASSIFIER_SYSTEM, t, CLASSIFIER_SCHEMA)
        if not data or data.get("kind") not in KINDS:
            return kind, False, "rules"
        kind, risk = data["kind"], bool(data.get("self_harm_risk"))
        # Sanity checks: the model's choice must fit what the words show.
        if kind == "recall" and not SHARED_HINT.search(t):
            kind = "fact" if is_question else "chat"
        if kind == "task" and not (TASK.search(t) or NETWORK_WORDS.search(t)):
            kind = "fact" if is_question else "chat"
        if kind in ("teach", "event", "chat") and is_question:
            kind = "fact"  # a question is never small talk: small talk lets the model speak freely
        if kind == "opinion" and re.search(r"\bmy\b", t):  # "what's my favorite color" asks a fact about you
            kind = "fact"
        return kind, risk, "the model"

    @staticmethod
    def _rules(t: str, is_question: bool) -> str:
        if TASK.search(t):
            return "task"
        if OPINION.search(t) and not re.search(r"\bmy\b", t):  # "my favorite color" is a fact about you
            return "opinion"
        if FEELING.search(t):
            return "emotional"
        if is_question:
            return "fact"
        return "chat"

