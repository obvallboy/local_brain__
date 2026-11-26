"""Tests against a real local model. Skipped unless FILECABINET_MODEL points to a GGUF file."""

import os
from pathlib import Path

import pytest

from filecabinet import Label

from .conftest import build

MODEL = os.environ.get("FILECABINET_MODEL", "")
pytestmark = pytest.mark.skipif(not Path(MODEL).is_file(), reason="set FILECABINET_MODEL to a GGUF file")


@pytest.fixture(scope="module")
def model():
    from filecabinet.model import LlamaModel

    return LlamaModel(MODEL)


def test_general_fact_is_i_think(model):
    answer = build(model=model).ask("What is the capital of France?")
    assert answer.label is Label.THINK
    assert "Paris" in answer.text


def test_personal_question_is_not_guessed(model):
    answer = build(model=model).ask("What was the name of my first dog?")
    assert answer.label is Label.NOT_SURE


def test_real_model_is_deterministic(model):
    cab = build(model=model)
    outputs = {cab.ask("Who wrote Romeo and Juliet?").render() for _ in range(5)}
    assert len(outputs) == 1


def test_deep_answer_is_guided_by_core(model):
    answer = build(model=model).ask("My best friend and I had a big fight")
    assert answer.label is Label.CORE
    assert len(answer.text) > 10


def test_drawer1_still_wins_over_the_model(model):
    answer = build(model=model).ask("What is my sister's name?")
    assert answer.label is Label.KNOW and answer.text == "Your sister's name is Maya."
