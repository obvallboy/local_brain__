"""Board recognition: naming a device and how to program it, from its USB id, offline."""

import pytest

from filecabinet import Label
from filecabinet.boards import identify
from filecabinet.devices import build, is_device_question, wants_help

from .conftest import build as build_cabinet


# ---- the recognizer ------------------------------------------------------------
def test_pico_by_exact_id():
    info = identify("2e8a", "0005")
    assert info.confidence == "exact" and "Pico" in info.name
    assert "MicroPython" in info.languages and info.voltage == "3.3 V"
    assert info.describe().startswith("This is a Raspberry Pi Pico")


def test_rp2040_by_vendor_when_pid_unknown():
    info = identify("2e8a", "ffff")
    assert info.confidence == "vendor" and info.chip == "RP2040"


def test_bridge_is_honest_about_the_board_behind_it():
    info = identify("1a86", "7523")
    assert info.is_bridge
    text = info.describe()
    assert "USB-to-serial chip, not a board" in text
    assert "could be an ESP32" in text
    # The redundant start of the note is trimmed, not repeated.
    assert text.count("not a board") == 1


def test_recognize_from_product_name_when_id_missing():
    info = identify(product="ESP32 NodeMCU")
    assert info.confidence == "hint" and info.chip == "ESP32"
    assert info.describe().startswith("This looks like")


def test_article_grammar():
    assert identify("2341", "0043").describe().startswith("This is an Arduino")
    assert identify(product="ESP32").describe().startswith("This looks like an ESP32")


def test_unknown_device_is_not_guessed():
    assert identify("ffff", "0000", "Mystery Widget") is None


def test_case_and_prefix_insensitive():
    assert identify("2E8A", "0x0005") is not None


# ---- the questions -------------------------------------------------------------
@pytest.mark.parametrize("text, is_dev, is_help", [
    ("what's plugged in", True, False),
    ("what is this", True, True),
    ("what board is this", True, True),
    ("how do i program my pico", True, True),
    ("how do i flash this esp32", True, True),
    ("what language does this board use", True, True),
    ("how do usb drives work", False, False),     # general: not a device question
    ("what's for dinner", False, False),
])
def test_question_detection(text, is_dev, is_help):
    assert is_device_question(text) is is_dev
    assert wants_help(text) is is_help


# ---- end to end through the cabinet --------------------------------------------
PICO = {"serial": [{"device": "COM5", "description": "USB Serial Device", "vid": "2e8a", "pid": "0005"}],
        "usb": [], "storage": [], "network": []}


def device_cabinet(snapshot=PICO):
    return build_cabinet(devices=lambda: snapshot)


def test_what_is_this_identifies_the_attached_board():
    answer = device_cabinet().ask("what is this plugged into com5?")
    assert answer.label is Label.CHECKED
    assert "Raspberry Pi Pico" in answer.text and "MicroPython" in answer.text


def test_how_do_i_program_my_pico():
    answer = device_cabinet().ask("how do i program my pico?")
    assert answer.label is Label.CHECKED
    assert "MicroPython" in answer.text and "115200" in answer.text


def test_whats_plugged_in_names_the_board():
    answer = device_cabinet().ask("what's plugged in?")
    assert "Raspberry Pi Pico" in answer.text


def test_program_question_about_an_absent_board_answers_from_the_registry():
    answer = device_cabinet(snapshot={"serial": [], "usb": [], "storage": [], "network": []}).ask(
        "how do i program an arduino uno?")
    assert answer.label is Label.KNOW
    assert "Arduino" in answer.text and "plugged in" in answer.text


def test_unknown_attached_board_is_admitted():
    snap = {"serial": [{"device": "COM9", "description": "Serial", "vid": "ffff", "pid": "0000"}],
            "usb": [], "storage": [], "network": []}
    answer = device_cabinet(snap).ask("what is this on com9?")
    assert answer.label is Label.CHECKED and "don't recognize" in answer.text
