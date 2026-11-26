import pytest

from filecabinet.temp import SCENARIOS

from .conftest import build

QUESTIONS = [
    "What is my sister's name?",
    "Do you think blue is pretty?",
    "Do you remember what color the car was that we saw earlier?",
    "Do you remember the boat we saw earlier?",
    "Websites won't load",
    "My best friend and I had a big fight",
    "What was the name of my first dog?",
]


@pytest.mark.parametrize("question", QUESTIONS)
def test_same_input_same_output_five_times(question, fake_model):
    cab = build(model=fake_model, network=SCENARIOS["dns"])
    outputs = {cab.ask(question).render() for _ in range(5)}
    assert len(outputs) == 1


def test_two_fresh_cabinets_agree(fake_model):
    a = [build(model=fake_model).ask(q).render() for q in QUESTIONS]
    b = [build(model=fake_model).ask(q).render() for q in QUESTIONS]
    assert a == b
