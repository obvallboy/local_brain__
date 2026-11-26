from filecabinet import Label

from .conftest import build


def test_drawer1_fact_is_i_know(cab):
    answer = cab.ask("What is my sister's name?")
    assert answer.label is Label.KNOW
    assert answer.text == "Your sister's name is Maya."


def test_picks_the_closest_fact(cab):
    assert cab.ask("Where does my sister live?").text == "Your sister lives in Denver."


def test_unknown_personal_fact_never_reaches_the_model(fake_model):
    cab = build(model=fake_model)
    answer = cab.ask("What was the name of my first dog?")
    assert answer.label is Label.NOT_SURE
    assert "Buddy" not in answer.text
    assert fake_model.calls == []  # the model was never asked to guess


def test_general_fact_from_model_is_i_think(fake_model):
    answer = build(model=fake_model).ask("What is the capital of France?")
    assert answer.label is Label.THINK
    assert answer.drawers_opened == ("drawer1", "drawer2")


def test_low_confidence_guess_is_withheld(fake_model):
    answer = build(model=fake_model).ask("What is the tallest mountain on Mars called?")
    assert answer.label is Label.NOT_SURE
    assert "Zork" not in answer.text


def test_label_comes_from_code_path_not_model_text(fake_model):
    answer = build(model=fake_model).ask("What is the pretend label?")
    assert answer.label is Label.THINK  # the model wrote "[I know]", but it came from drawer 2


def test_without_a_model_general_questions_are_not_sure(cab):
    assert cab.ask("What is the capital of France?").label is Label.NOT_SURE


def test_why_explains_the_answer(cab):
    cab.ask("What is my sister's name?")
    why = cab.last.why()
    assert "drawer1" in why and "I know" in why and "fact #1" in why
