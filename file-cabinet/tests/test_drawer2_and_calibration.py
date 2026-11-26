from filecabinet import Label
from filecabinet.cabinet import ask_drawer2
from filecabinet.calibrate import KNOWN, MADE_UP, measure
from filecabinet.model import ModelReply, load_threshold

from .conftest import FakeModel, build


def test_unknown_is_not_an_answer():
    reply, why = ask_drawer2(FakeModel(default=ModelReply("unknown", 0.99)), "who invented the flarn engine")
    assert reply is None and "doesn't know" in why


def test_repeating_the_question_is_not_an_answer():
    model = FakeModel(default=ModelReply("Petrin Vale", 0.6))
    reply, why = ask_drawer2(model, "who wrote the novel the glass orchard of petrin vale")
    assert reply is None and "repeated the question" in why


def test_a_calibrated_model_uses_its_own_cutoff():
    model = FakeModel(default=ModelReply("Tokyo", 0.2))
    assert ask_drawer2(model, "capital of japan")[0] is None  # default cutoff 0.35
    model.threshold = 0.15
    assert ask_drawer2(model, "capital of japan")[0].text == "Tokyo"


def test_withheld_guess_is_explained(fake_model):
    answer = build(model=fake_model).ask("What is the tallest mountain on Mars called?")
    assert answer.label is Label.NOT_SURE
    assert any("withheld" in e for e in answer.evidence)


def test_calibration_sets_the_cutoff_above_every_wrong_answer():
    right = {q: ModelReply(words[0].title(), 0.9) for q, words in KNOWN}
    invented = {q: ModelReply("Someone Smith", 0.42) for q in MADE_UP[:3]}
    model = FakeModel(replies={**right, **invented}, default=ModelReply("unknown", 0.9))
    result = measure(model)
    assert result["threshold"] == 0.5  # 0.42 + 0.05 is below the 0.5 floor
    assert result["right_answers_kept"] == len(KNOWN)
    assert result["wrong_or_invented_seen"] == 3


def test_a_confident_wrong_answer_raises_the_cutoff():
    right = {q: ModelReply(words[0].title(), 0.95) for q, words in KNOWN}
    model = FakeModel(replies={**right, MADE_UP[0]: ModelReply("Queen Alba", 0.7)}, default=ModelReply("unknown", 0.9))
    assert measure(model)["threshold"] == 0.75


def test_uncalibrated_model_gets_the_default(tmp_path):
    assert load_threshold(str(tmp_path / "missing.gguf")) == 0.35
