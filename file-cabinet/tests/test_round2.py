"""Round 2: natural wording, forgetting, device-question precision, time phrases."""

from datetime import datetime

import pytest

from filecabinet import Label
from filecabinet.commands import run_command
from filecabinet.devices import is_device_question
from filecabinet.frontdesk import FrontDesk
from filecabinet.recall import time_window

from .conftest import NOW, FakeModel, build


# ---- natural wording -----------------------------------------------------------
@pytest.mark.parametrize("statement, question, word", [
    ("remember that my locker code is 4312", "what's my locker code", "4312"),
    ("fyi my dentist is dr patel", "who is my dentist", "patel"),
    ("btw my birthday is march 3rd", "when is my birthday", "march"),
    ("leo is my brother", "who is leo", "brother"),
    ("just so you know i'm allergic to peanuts", "what am i allergic to", "peanuts"),
    ("i drive a red truck", "what do i drive", "truck"),
    ("i'm 15", "how old am i", "15"),
])
def test_learns_from_natural_wording(cab, statement, question, word):
    assert cab.ask(statement).label is Label.FILED
    answer = cab.ask(question)
    assert answer.label is Label.KNOW and word in answer.text.lower()


def test_remember_that_is_telling_not_asking():
    assert FrontDesk().route("remember that my locker code is 4312").kind == "teach"
    assert FrontDesk().route("do you remember my locker code?").kind == "recall"


def test_this_is_my_is_not_a_fact_about_a_person():
    assert FrontDesk().route("this is my house").kind != "teach"


def test_model_rewrites_unusual_facts_using_only_your_words():
    said = "the code for my bike lock is 1234"
    model = FakeModel(classify={said: {"kind": "teach", "self_harm_risk": False,
                                       "subject": "bike lock", "fact": "The code for your bike lock is 1234."}})
    cab = build(model=model)
    filed = cab.ask(said)
    assert filed.label is Label.FILED and "understood by the model" in filed.evidence[0]
    assert cab.ask("what's the code for my bike lock").label is Label.KNOW


def test_model_cannot_add_words_you_didnt_say():
    said = "the code for my bike lock is 1234"
    model = FakeModel(classify={said: {"kind": "teach", "self_harm_risk": False, "subject": "bike lock",
                                       "fact": "Your bike lock code is 9999 and you live in Paris."}})
    assert build(model=model).ask(said).label is Label.NOT_SURE


# ---- forgetting -------------------------------------------------------------------
def test_forget_removes_a_fact(cab):
    cab.ask("my locker code is 4312")
    removed = cab.ask("forget my locker code")
    assert removed.label is Label.REMOVED and "4312" in removed.text
    assert cab.ask("what's my locker code").label is Label.NOT_SURE


def test_forget_removes_older_versions_too(cab):
    cab.ask("my sister's name is mia")  # replaces "Maya" from the fixture
    cab.ask("forget my sister's name")
    answer = cab.ask("what's my sister's name")
    assert answer.label is not Label.KNOW or "Maya" not in answer.text


def test_forgetting_something_unknown(cab):
    answer = cab.ask("forget my passport number")
    assert answer.label is Label.NOT_SURE and "nothing to forget" in answer.text


def test_i_forgot_is_not_a_request():
    assert FrontDesk().route("i forgot my keys at the park").kind != "forget"


def test_facts_and_forget_commands(cab):
    listing = run_command(cab, "/facts sister")
    assert "#1 sister: Your sister's name is Maya." in listing
    assert run_command(cab, "/forget 1") == "Removed fact #1 from drawer 1."
    assert run_command(cab, "/forget 1") == "There's no fact #1."


def test_core_memories_cannot_be_forgotten(cab):
    pid = cab.store.propose_core("Grandpa taught you to fish.")
    cab.core.approve(pid, "owner")
    cab.ask("forget that grandpa taught me to fish")
    assert cab.store.core_memories()  # still there: drawer 3 is append-only


# ---- device questions ---------------------------------------------------------------
@pytest.mark.parametrize("text, expected", [
    ("what's plugged in", True),
    ("is my arduino connected", True),
    ("which com port is my arduino on", True),
    ("do i have any serial ports", True),
    ("is anything new showing up on usb", True),
    ("is my mouse detected", True),
    ("what devices do you recommend for a smart home", False),
    ("how do usb drives work", False),
    ("what is a dev board", False),
    ("is my wifi connected", False),
])
def test_device_question_precision(text, expected):
    assert is_device_question(text) is expected


# ---- time phrases (NOW is Wednesday 2026-11-25, 15:00) ------------------------------
@pytest.mark.parametrize("phrase, start, end", [
    ("on monday", datetime(2026, 11, 23), datetime(2026, 11, 24)),
    ("three days ago", datetime(2026, 11, 22), datetime(2026, 11, 23)),
    ("2 days ago", datetime(2026, 11, 23), datetime(2026, 11, 24)),
    ("last weekend", datetime(2026, 11, 21), datetime(2026, 11, 23)),
    ("this morning", datetime(2026, 11, 25), datetime(2026, 11, 25, 12)),
    ("last wednesday", datetime(2026, 11, 18), datetime(2026, 11, 19)),
    ("this week", datetime(2026, 11, 23), datetime(2026, 11, 26)),
])
def test_time_windows(phrase, start, end):
    assert time_window(f"what did we do {phrase}", NOW) == (start, end)


def test_what_did_we_do_on_a_day(cab):
    cab.store.log_episode("School", "watching", "Watched the robotics club demo.", ts=datetime(2026, 11, 23, 17))
    answer = cab.ask("what did we do on monday")
    assert answer.label is Label.REMEMBER and "robotics" in answer.text


def test_the_wrong_day_is_not_a_memory(cab):
    cab.store.log_episode("Ridge Trail", "hiking", "Hiked the ridge trail.", ts=datetime(2026, 11, 21, 10))
    assert cab.ask("did we go hiking on monday").label is Label.DONT_REMEMBER
