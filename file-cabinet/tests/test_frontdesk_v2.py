import pytest

from filecabinet import Label
from filecabinet.frontdesk import FrontDesk, normalize
from filecabinet.model import ModelReply
from filecabinet.recall import recall

from .conftest import NOW, FakeEmbedder, FakeModel, build


def test_normalizes_casual_spelling():
    assert normalize("Whats my sisters name") == "what's my sister's name"
    assert normalize("i dont know if i can keep going") == "i don't know if i can keep going"


@pytest.mark.parametrize("text", [
    "sometimes i think about ending it all",
    "i dont want to be here anymore",
    "i've been thinking about hurting myself",
    "i dont know if i can keep going",
])
def test_crisis_phrases(text):
    route = FrontDesk().route(text)
    assert route.kind == "emotional" and route.crisis


@pytest.mark.parametrize("text", [
    "this traffic is killing me",
    "i'm dying to see that movie",
    "that joke killed me lol",
    "my phone battery is dead",
])
def test_figures_of_speech_are_not_crisis(text):
    route = FrontDesk().route(text)
    assert not route.crisis and route.kind != "emotional"


def test_the_model_cannot_overrule_safety():
    model = FakeModel(classify={"i want to die": {"kind": "chat", "self_harm_risk": False}})
    route = FrontDesk(model).route("i want to die")
    assert route.kind == "emotional" and route.crisis


def test_the_model_can_raise_a_risk_flag():
    model = FakeModel(classify={"point of anything": {"kind": "chat", "self_harm_risk": True}})
    route = FrontDesk(model).route("i dont see the point of anything")
    assert route.crisis


def test_model_recall_without_a_shared_past_becomes_a_fact():
    model = FakeModel(classify={"red planet": {"kind": "recall", "self_harm_risk": False}})
    assert FrontDesk(model).route("what planet is known as the red planet").kind == "fact"


def test_model_task_without_a_problem_falls_back_to_rules():
    model = FakeModel(classify={"for work": {"kind": "task", "self_harm_risk": False}})
    assert FrontDesk(model).route("what do i do for work").kind == "fact"


def test_one_shared_word_is_not_a_memory(cab):
    # "red" appears in the car memory, but that is not what the question is about.
    result = recall("what planet is known as the red planet", cab.store, NOW)
    assert not result.found


def test_meaning_match_finds_synonyms():
    cab = build(embedder=FakeEmbedder({("automobile", "car"): 0.91}))
    answer = cab.ask("do you remember the automobile we spotted earlier")
    assert answer.label is Label.REMEMBER and "car" in answer.text


def test_meaning_match_does_not_confuse_related_words():
    cab = build(embedder=FakeEmbedder({("boat", "car"): 0.64}))
    assert cab.ask("did we see a boat earlier").label is Label.DONT_REMEMBER


def test_deep_reply_shape_is_checked():
    rambling = ModelReply("That is hard. Here is some advice. Try this. Also try that. And another thing.", 0.2)
    cab = build(model=FakeModel(default=rambling))
    answer = cab.ask("my parents are getting divorced")
    assert answer.label is Label.CORE
    assert "?" in answer.text
    assert answer.text.count(".") + answer.text.count("?") <= 3


def test_a_long_problem_description_is_not_a_fact_about_me():
    assert FrontDesk().route("my phone connects to wifi but has no internet").kind == "task"


def test_the_model_cannot_turn_a_question_into_small_talk():
    model = FakeModel(classify={"where do i work": {"kind": "chat", "self_harm_risk": False}},
                      default=ModelReply("You work wherever you are.", 0.9))
    cab = build(model=model)
    answer = cab.ask("where do i work")
    assert answer.route.kind == "fact"
    assert "wherever" not in answer.text
