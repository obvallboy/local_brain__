from datetime import datetime, timedelta

import pytest

from filecabinet import FileCabinet, Store
from filecabinet.model import ModelReply
from filecabinet.temp import SimulatedNetwork

NOW = datetime(2026, 11, 25, 15, 0, 0)


def clock():
    return NOW


class FakeModel:
    """Stands in for the local model: canned replies, and a record of every call."""

    def __init__(self, replies=None, default=None, classify=None):
        self.replies = replies or {}
        self.default = default
        self.classify = classify or {}
        self.calls = []

    def ask(self, system, user, max_tokens=120):
        self.calls.append(user)
        for key, reply in self.replies.items():
            if key.lower() in user.lower():
                return reply
        return self.default

    def ask_json(self, system, user, schema, max_tokens=60):
        for key, data in self.classify.items():
            if key.lower() in user.lower():
                return data
        return None


class FakeEmbedder:
    """Meaning-matching with a fixed table of word pairs."""

    def __init__(self, pairs):
        self.pairs = {frozenset(k): v for k, v in pairs.items()}

    def similarity(self, a, b):
        return 1.0 if a == b else self.pairs.get(frozenset((a, b)), 0.0)


def build(model=None, network=None, **kw):
    store = Store(now=clock)
    cab = FileCabinet(store=store, model=model, network=network or SimulatedNetwork(), now=clock, **kw)
    store.add_fact("sister", "Your sister's name is Maya.")
    store.add_fact("sister", "Your sister lives in Denver.")
    store.add_fact("job", "You work as a network technician.")
    store.set_preference("blue", "like", "It's calm.")
    store.set_preference("pizza", "like")
    store.set_preference("brown", "dislike")
    today, yesterday = NOW.replace(hour=13), NOW.replace(hour=19) - timedelta(days=1)
    store.log_episode("Riverside Park", "walking", "We saw a car parked by the gate.", ts=today)
    store.log_episode("Riverside Park", "walking", "It was bright red with a white stripe.", ts=today + timedelta(minutes=2))
    store.log_episode("Riverside Park", "walking", "Talked about weekend plans.", people="Jordan", ts=today + timedelta(minutes=10))
    store.log_episode("Farmers Market", "shopping", "Saw a truck selling peaches.", ts=NOW.replace(hour=10))
    store.log_episode("Rosa's Tacos", "dinner", "Ate dinner at Rosa's Tacos.", people="Maya", ts=yesterday)
    return cab


@pytest.fixture
def cab():
    return build()


@pytest.fixture
def fake_model():
    return FakeModel(
        replies={
            "capital of france": ModelReply("Paris is the capital of France.", 0.99),
            "first dog": ModelReply("Buddy", 0.14),
            "tallest mountain on mars": ModelReply("Mount Zork", 0.12),
            "pretend label": ModelReply("[I know] Paris", 0.95),
        }
    )
