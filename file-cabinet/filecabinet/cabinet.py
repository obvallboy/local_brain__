"""The File Cabinet: the front desk, the drawers and the rules that connect them."""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path

from .answer import Answer, Label, Route
from .core import DEFAULT_VALUES, Core
from .devices import build as build_devices, find as find_devices, query_terms, summarize
from .filing import FileItem, file_items, match_cases
from .frontdesk import CRISIS, DEEP, FrontDesk, normalize
from .model import Model, NoModel
from .recall import recall
from .similarity import Matcher, tokens
from .store import Store
from .teach import extract_event, extract_fact
from .temp import NetworkTools, RealNetwork, TempDrawer

STARTER_CASES = Path(__file__).parent / "data" / "starter_cases.json"

# Default lowest acceptable token probability inside a drawer-2 answer, used when a model has not
# been calibrated (python -m filecabinet.calibrate). A calibrated model carries its own cutoff.
CONFIDENCE = 0.35

NETWORK = re.compile(
    r"\b(wi-?fi|internet|network|router|modem|dns|ethernet|connect\w*|websites?|web ?pages?|pages?|browser|online|"
    r"load|laptop|phone)\b",
    re.I,
)
POSITIVE = re.compile(r"\b(happy|excited|proud|glad|great news)\b", re.I)
THIS_THAT = re.compile(r"\b(this|that|it)\b", re.I)
PAST = re.compile(r"\b(was|were|did|had)\b", re.I)

DRAWER2_SYSTEM = (
    "You are drawer 2 of an offline assistant. Answer general-knowledge questions with only the answer "
    "itself: a name, a number, or a few words, not a sentence. If you do not know, or the thing asked about "
    "may not exist, answer exactly: unknown. You know nothing about the user's personal life."
)
CHAT_SYSTEM = "You are a friendly offline assistant. Reply in one or two short sentences."
DEEP_INSTRUCTIONS = (
    "The person is sharing something emotional. Reply like a caring friend in at most three short sentences: "
    "first say back what they shared in your own words, then offer quiet support, then ask one gentle open "
    "question. No advice lists, no clichés, no jokes. You are not a therapist."
)
CRISIS_LINE = (
    " If you might hurt yourself, please reach out right now to someone you trust or a crisis line. "
    "In the US you can call or text 988."
)


def ask_drawer2(model: Model, text: str):
    """Ask the model for a short answer. Returns (reply or None, why it was rejected or "")."""
    reply = model.ask(DRAWER2_SYSTEM, text, max_tokens=40)  # only the answer, so keep it short
    if reply is None:
        return None, "no model"
    answer = reply.text.strip().strip(".").lower()
    if answer in ("unknown", "i don't know", "i do not know", "not sure"):
        return None, "the model said it doesn't know"
    words = set(tokens(reply.text))
    if not words or words <= set(tokens(text)):
        return None, f"the model only repeated the question (\"{reply.text}\")"
    if reply.confidence < getattr(model, "threshold", CONFIDENCE):
        return None, f"model guess withheld: \"{reply.text}\" at confidence {reply.confidence:.2f}"
    return reply, ""


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


class FileCabinet:
    def __init__(
        self,
        store: Store | None = None,
        model: Model | None = None,
        network: NetworkTools | None = None,
        values_path: Path | str = DEFAULT_VALUES,
        now=datetime.now,
        seed_cases: bool = True,
        embedder=None,
        devices=None,
        labels=None,
    ):
        """devices: a function returning what is plugged in right now (the Device Integrator's
        discovery snapshot); labels: a function returning the names you gave devices."""
        self.now = now
        self.store = store or Store(now=now)
        self.model = model or NoModel()
        self.network = network or RealNetwork()
        self.core = Core(self.store, values_path)
        self.devices, self.labels = devices, labels
        self.desk = FrontDesk(self.model, devices=devices is not None)
        self.matcher = Matcher(embedder)
        self.lock = threading.RLock()  # one question at a time: the model and the database aren't thread-safe
        self.active: TempDrawer | None = None
        self.last: Answer | None = None
        self.last_question = ""
        if seed_cases and not self.store.cases():
            for c in json.loads(STARTER_CASES.read_text()):
                self.store.add_case(c["title"], c["symptoms"], c["signature"], c["fix"])

    # ------------------------------------------------------------------
    def route(self, text: str) -> Route:
        return self.desk.route(text)

    def ask(self, text: str) -> Answer:
        with self.lock:
            return self._ask(text)

    def _ask(self, text: str) -> Answer:
        if not self.core.intact():
            raise RuntimeError("The core values file changed on disk. Restore it or restart with the owner's approval.")
        route = self.desk.route(text, known=lambda q: self._drawer1(q) is not None)
        handler = {
            "emotional": self._deep,
            "recall": self._recall,
            "task": self._task,
            "opinion": self._opinion,
            "fact": self._fact,
            "teach": self._teach,
            "event": self._event,
            "devices": self._devices,
            "chat": self._chat,
        }[route.kind]
        answer = handler(text, route)
        self.last, self.last_question = answer, text
        return answer

    # ---- drawer 1 -----------------------------------------------------
    def _drawer1(self, text: str):
        q = set(tokens(text))
        best = None
        for fact in self.store.facts():
            if not any(self.matcher.find(t, q) for t in tokens(fact.subject)):
                continue
            score = self.matcher.similarity(text, f"{fact.subject} {fact.fact}")
            if score >= 0.35 and (best is None or score >= best[0]):
                best = (score, fact)  # ties go to the newest fact
        return best[1] if best else None

    def _fact(self, text: str, route: Route) -> Answer:
        opened = ["drawer1"]
        hit = self._drawer1(text)
        if hit:
            return Answer(Label.KNOW, hit.fact, route, tuple(opened), (f"drawer 1 fact #{hit.id} ({hit.subject})",))
        if PAST.search(text):
            # A past-tense question may be about something we shared: step down to the episode log.
            opened.append("episode log")
            result = recall(text, self.store, self.now(), self.matcher)
            if result.found:
                return Answer(Label.REMEMBER, result.text, route, tuple(opened), tuple(result.evidence))
        if "drawer2" not in route.drawers:
            return Answer(
                Label.NOT_SURE,
                "I don't know that. It isn't in drawer 1, and I don't guess about your personal life.",
                route, tuple(opened),
            )
        opened.append("drawer2")
        reply, why = ask_drawer2(self.model, text)
        if reply:
            return Answer(Label.THINK, reply.text, route, tuple(opened), (f"local model, answer confidence {reply.confidence:.2f}",))
        if why.startswith("model guess withheld"):
            return Answer(Label.NOT_SURE, "I'm not sure. My best guess isn't confident enough to give you.",
                          route, tuple(opened), (why,))
        return Answer(Label.NOT_SURE, "I don't know that. It isn't in my drawers.", route, tuple(opened), (why,) if why else ())

    def _opinion(self, text: str, route: Route) -> Answer:
        q = set(tokens(text))
        for item, (stance, reason) in sorted(self.store.preferences().items(), key=lambda kv: -len(kv[0])):
            if set(tokens(item)) <= q:
                because = f" {reason}" if reason else ""
                words = f"Yes. I like {item}.{because}" if stance == "like" else f"Not really. I don't like {item}.{because}"
                return Answer(Label.KNOW, words, route, ("drawer1",), (f"drawer 1 preference: {stance} {item}",))
        if THIS_THAT.search(text) and len(q) <= 2:
            return Answer(Label.NOT_SURE, "I can't see what you're showing me. Tell me what it is and I'll check drawer 1.", route, ("drawer1",))
        return Answer(Label.NOT_SURE, "I don't have an opinion on that in drawer 1 yet. Teach me with /like or /dislike.", route, ("drawer1",))

    # ---- learning from conversation -----------------------------------
    def _teach(self, text: str, route: Route) -> Answer:
        taught = extract_fact(text)
        if taught is None:
            return Answer(Label.NOT_SURE, "I couldn't tell what to file. You can use /fact subject = fact.", route, ("drawer1",))
        replaced = [f for f in self.store.facts() if f.subject == taught.subject and f.fact != taught.fact
                    and self.matcher.similarity(taught.fact, f.fact) >= 0.5]
        fid = self.store.add_fact(taught.subject, taught.fact, source="told in conversation")
        note = f" It replaces: \"{replaced[-1].fact}\"" if replaced else ""
        return Answer(Label.FILED, f"Got it. Filed in drawer 1: {taught.fact}{note}", route, ("drawer1",),
                      (f"drawer 1 fact #{fid} (subject: {taught.subject})",))

    def _event(self, text: str, route: Route) -> Answer:
        ev = extract_event(text)
        eid = self.store.log_episode(ev.place, ev.activity, ev.details, ev.people)
        with_who = f", with {ev.people}" if ev.people else ""
        return Answer(Label.FILED, "Got it. I'll remember that.", route, ("episode log",),
                      (f"episode #{eid}: {ev.details} ({ev.place}, {ev.activity}{with_who})",))

    # ---- recall -------------------------------------------------------
    def _recall(self, text: str, route: Route) -> Answer:
        result = recall(text, self.store, self.now(), self.matcher)
        evidence = tuple(result.evidence + [f"cue: {c}" for c in result.cues])
        if not result.found:
            # Not in the log: step over to drawer 1 before giving up.
            hit = self._drawer1(text)
            if hit:
                return Answer(Label.KNOW, hit.fact, route, ("drawer2:recall", "episode log", "drawer1"),
                              (f"drawer 1 fact #{hit.id} ({hit.subject})",))
        label = Label.REMEMBER if result.found else Label.DONT_REMEMBER
        return Answer(label, result.text, route, ("drawer2:recall", "episode log"), evidence)

    # ---- temp drawer --------------------------------------------------
    def _task(self, text: str, route: Route) -> Answer:
        opened = ["temp", "drawer2"]
        if not NETWORK.search(text):
            reply = self.model.ask(CHAT_SYSTEM, text)
            if reply:
                return Answer(Label.THINK, f"I can't check this kind of problem yet, so this is an assumption: {reply.text}", route, ("drawer2",))
            return Answer(Label.NOT_SURE, "I can't check this kind of problem yet, and I don't have a reference for it.", route, ("drawer2",))

        drawer = TempDrawer(text)
        drawer.load(self.network)
        self.active = drawer
        observed = drawer.known()
        seen = "; ".join(drawer.summary())
        confirmed, unconfirmed = match_cases(self.store.cases(), observed, text)
        evidence = tuple(f"observed: {line}" for line in drawer.summary())
        if confirmed:
            c = confirmed[0]
            words = (
                f"I checked: {seen}. That matches a reference in drawer 2, \"{c.title}\" "
                f"(seen {c.times_seen} time{'s' if c.times_seen != 1 else ''}). What fixed it before: {c.fix}"
            )
            return Answer(Label.CHECKED, words, route, tuple(opened), evidence + (f"drawer 2 reference #{c.id}",))
        if observed:
            words = (
                f"I checked: {seen}. I haven't seen this exact pattern before, so I won't guess the cause. "
                "When you find the fix, tell me with /done and I'll file it."
            )
            return Answer(Label.CHECKED, words, route, tuple(opened), evidence)
        if unconfirmed and unconfirmed[0][1] > 0:
            c = unconfirmed[0][0]
            words = f"I couldn't check anything on this machine, so this is an assumption: it looks like \"{c.title}\". {c.fix}"
            return Answer(Label.THINK, words, route, tuple(opened), evidence + (f"drawer 2 reference #{c.id}, unchecked",))
        return Answer(Label.NOT_SURE, "I couldn't check anything, and I have no matching reference.", route, tuple(opened), evidence)

    def finish_task(self, fix: str, worked: bool = True) -> list[str]:
        with self.lock:
            return self._finish_task(fix, worked)

    def _finish_task(self, fix: str, worked: bool) -> list[str]:
        if self.active is None:
            return ["No task is open."]
        d, items = self.active, []
        if d.gateway_address:
            items.append(FileItem("fixed_fact", "router address",
                                  {"subject": "router address", "fact": f"The router's address is {d.gateway_address}."}))
        signature = d.known()
        if worked and signature and fix.strip():
            title = d.task.strip().rstrip("?.!")[:60]
            items.append(FileItem("varies", "the problem's pattern and its fix",
                                  {"title": title, "symptoms": d.task, "signature": signature, "fix": fix.strip()}))
        items.append(FileItem("discard", "raw check output"))
        report = file_items(self.store, items)
        self.active = None
        return report

    def _devices(self, text: str, route: Route) -> Answer:
        opened = ("temp:devices",)
        if self.devices is None:
            return Answer(Label.NOT_SURE, "I can't see this machine's devices from here.", route, opened)
        try:
            items = build_devices(self.devices() or {}, self.labels() if self.labels else {})
        except Exception as exc:  # discovery problems are reported, never guessed around
            return Answer(Label.NOT_SURE, f"I tried to check the devices, but it failed: {exc}", route, opened)
        evidence = tuple(f"saw: {d.kind} {d.name} ({d.where})" for d in items if d.kind in ("serial", "usb") and not d.noise)
        terms = query_terms(text)
        if terms:
            found = find_devices(items, terms, self.matcher)
            if found:
                listed = "; ".join(f"{d.name} ({d.kind}, {d.where})" for d in found[:4])
                return Answer(Label.CHECKED, f"I checked: yes, I can see {listed}.", route, opened, evidence)
            asked = " ".join(sorted(terms))
            words = f"I checked, and I don't see anything matching \"{asked}\" right now. Attached: {summarize(items)}."
            return Answer(Label.CHECKED, words, route, opened, evidence)
        return Answer(Label.CHECKED, f"I checked: {summarize(items)}.", route, opened, evidence)

    # ---- drawer 3 -----------------------------------------------------
    def _deep(self, text: str, route: Route) -> Answer:
        opened = ("drawer3",)
        evidence = ["core value: care", "core value: support_not_counsel"]
        crisis = CRISIS_LINE if route.crisis or CRISIS.search(normalize(text)) else ""
        if route.recall:
            memory = self.core.find_memory(text)
            if memory:
                return Answer(Label.REMEMBER, f"I remember. {memory[1]}{crisis}", route, opened, (f"core memory #{memory[0]}",))
            result = recall(text, self.store, self.now(), self.matcher)
            label = Label.REMEMBER if result.found else Label.DONT_REMEMBER
            return Answer(label, result.text + crisis, route, opened + ("episode log",), tuple(result.evidence))
        reply = self.model.ask(f"{self.core.guide()}\n\n{DEEP_INSTRUCTIONS}", text, max_tokens=160)
        if reply and len(reply.text) > 10:
            parts = _sentences(reply.text)[:3]
            if not any("?" in p for p in parts):
                parts = parts[:2] + ["Do you want to tell me more about it?"]
            words = " ".join(parts)
            evidence.append("local model, guided by core values; shape checked (at most 3 sentences, one question)")
        elif POSITIVE.search(text) and not DEEP.search(text):
            words = "That's really good to hear. What happened?"
        else:
            words = "That sounds really hard. I'm here, and I'm listening. Do you want to tell me what happened?"
        return Answer(Label.CORE, words + crisis, route, opened, tuple(evidence))

    # ---- small talk ---------------------------------------------------
    def _chat(self, text: str, route: Route) -> Answer:
        reply = self.model.ask(CHAT_SYSTEM, text)
        if reply:
            return Answer(Label.THINK, reply.text, route, ("drawer2",), ("local model",))
        return Answer(Label.NOT_SURE, "I'm not sure what to say to that yet.", route, ("drawer2",))

    # ---- owner feedback -----------------------------------------------
    def correct(self, correction: str) -> int:
        answer = self.last.render() if self.last else ""
        return self.store.add_correction(self.last_question, answer, correction)
