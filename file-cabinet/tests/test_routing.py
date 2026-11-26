import pytest

from filecabinet.frontdesk import FrontDesk

desk = FrontDesk()


@pytest.mark.parametrize(
    "question, kind, drawers",
    [
        ("Do you think blue is pretty?", "opinion", ("drawer1",)),
        ("Is this funny?", "opinion", ("drawer1",)),
        ("Do you remember the color of the car we saw earlier?", "recall", ("drawer2:recall",)),
        ("My wifi keeps dropping, can you fix it?", "task", ("temp", "drawer2")),
        ("Websites won't load", "task", ("temp", "drawer2")),
        ("What is my sister's name?", "fact", ("drawer1",)),
        ("What is the capital of France?", "fact", ("drawer1", "drawer2")),
        ("My best friend and I had a big fight", "emotional", ("drawer3",)),
        ("I feel kind of off today", "emotional", ("drawer3",)),
        ("hello there", "chat", ("drawer2",)),
    ],
)
def test_route(question, kind, drawers):
    route = desk.route(question)
    assert route.kind == kind
    assert route.drawers == drawers


def test_deep_beats_everything_else():
    # A heavy question is never treated as an opinion or small talk.
    route = desk.route("Do you think it's funny that my dog died?")
    assert route.kind == "emotional" and route.depth == "deep"


def test_deep_recall_is_flagged():
    route = desk.route("Do you remember the summer before grandpa died?")
    assert route.kind == "emotional" and route.recall


def test_lost_keys_is_not_deep():
    assert desk.route("I lost my keys, do you remember where I put them?").kind == "recall"


def test_opinion_opens_only_drawer1(cab):
    answer = cab.ask("Do you think blue is pretty?")
    assert answer.drawers_opened == ("drawer1",)
