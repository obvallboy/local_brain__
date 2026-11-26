"""Features a host app (like the Device Integrator) relies on."""

import json
import threading

from filecabinet import Label
from filecabinet.commands import run_command
from filecabinet.devices import build, find, summarize
from filecabinet.model import find_models

from .conftest import build as build_cabinet

SNAPSHOT = {
    "serial": [
        {"device": "COM3", "description": "USB-SERIAL CH340", "manufacturer": "wch.cn", "vid": "1a86", "pid": "7523"},
        {"device": "COM5", "description": "Silicon Labs CP210x", "vid": "10c4", "pid": "ea60"},
    ],
    "usb": [
        {"vid": "1d6b", "pid": "0002", "product": "EHCI Host Controller root hub", "device_class_name": "Hub", "bus": "1", "address": "1"},
        {"vid": "046d", "pid": "c52b", "product": "USB Receiver", "manufacturer": "Logitech", "bus": "1", "address": "4"},
    ],
    "storage": [{"device": "C:\\", "mountpoint": "C:\\", "fstype": "NTFS"}],
    "network": [{"name": "Wi-Fi", "is_up": True, "addresses": [{"address": "192.168.1.42"}]},
                {"name": "Ethernet", "is_up": False}],
}
LABELS = {"serial:COM3": {"label": "Arduino Uno", "note": "pin 13 led; 9600 baud"}}


def device_cabinet():
    return build_cabinet(devices=lambda: SNAPSHOT, labels=lambda: LABELS)


def test_summary_uses_your_labels_and_skips_hubs():
    text = summarize(build(SNAPSHOT, LABELS))
    assert "Arduino Uno on COM3" in text
    assert "root hub" not in text
    assert "1 network interface up" in text


def test_find_by_label_or_description():
    items = build(SNAPSHOT, LABELS)
    assert [d.where for d in find(items, {"arduino"})] == ["COM3"]
    assert [d.where for d in find(items, {"cp210x"})] == ["COM5"]


def test_whats_plugged_in():
    answer = device_cabinet().ask("what's plugged in right now?")
    assert answer.label is Label.CHECKED
    assert answer.route.kind == "devices"
    assert "Arduino Uno on COM3" in answer.text


def test_is_my_arduino_connected():
    answer = device_cabinet().ask("is my arduino connected?")
    assert answer.label is Label.CHECKED and "Arduino Uno (serial, COM3)" in answer.text


def test_missing_device_is_reported_not_guessed():
    answer = device_cabinet().ask("is my esp32 plugged in?")
    assert answer.label is Label.CHECKED
    assert "don't see anything matching" in answer.text and "esp32" in answer.text


def test_device_questions_need_a_device_source(cab):
    # Without a host app supplying devices, the question goes elsewhere.
    assert cab.ask("is my arduino plugged in?").route.kind != "devices"


def test_failing_discovery_is_reported():
    def broken():
        raise OSError("permission denied")
    answer = build_cabinet(devices=broken).ask("what devices are attached?")
    assert answer.label is Label.NOT_SURE and "permission denied" in answer.text


def test_export_and_import_between_machines(tmp_path):
    laptop = build_cabinet()
    laptop.ask("my brother's name is leo")
    pid = laptop.store.propose_core("Something that shaped me.")
    laptop.core.approve(pid, "owner")
    data = laptop.store.export_data()

    desktop = build_cabinet(seed_cases=False)
    added = desktop.store.import_data(json.loads(json.dumps(data)))
    assert added["facts"] >= 1 and added["episodes"] == 0  # same episodes were already there
    assert desktop.ask("what's my brother's name").label is Label.KNOW
    # Core memories arrive as proposals: drawer 3 still needs the owner.
    assert desktop.store.core_memories() == []
    assert added["core_proposals"] == 1
    # Importing twice adds nothing.
    assert sum(desktop.store.import_data(data).values()) == 0


def test_import_rejects_other_files():
    try:
        build_cabinet().store.import_data({"hello": 1})
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_export_import_commands(tmp_path):
    cab = build_cabinet()
    out = tmp_path / "brain.json"
    assert "Saved" in run_command(cab, f"/export {out}")
    other = build_cabinet(seed_cases=False)
    assert run_command(other, f"/import {out}").startswith("Imported:")


def test_safe_to_use_from_several_threads():
    cab = build_cabinet()
    errors = []

    def worker(i):
        try:
            for _ in range(20):
                cab.ask(f"my friend number {i} is named sam{i}")
                cab.ask("what is my sister's name?")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


def test_find_models_picks_the_biggest_chat_model(tmp_path):
    (tmp_path / "qwen2.5-1.5b-instruct-q4_k_m.gguf").write_bytes(b"x" * 10)
    (tmp_path / "qwen2.5-3b-instruct-q4_k_m.gguf").write_bytes(b"x" * 20)
    (tmp_path / "bge-small-en-v1.5-f16.gguf").write_bytes(b"x" * 30)
    chat, embed = find_models(tmp_path)
    assert chat.endswith("qwen2.5-3b-instruct-q4_k_m.gguf")
    assert embed.endswith("bge-small-en-v1.5-f16.gguf")
    assert find_models(tmp_path / "missing") == (None, None)


def test_placeholder_names_are_cleaned():
    items = build({"serial": [{"device": "/dev/ttyS0", "description": "n/a"}]})
    assert items[0].name == "/dev/ttyS0"


def test_known_answers_skip_the_model():
    from filecabinet.model import ModelReply

    from .conftest import FakeModel
    model = FakeModel(default=ModelReply("x", 0.9), classify={"": {"kind": "chat", "self_harm_risk": False}})
    cab = build_cabinet(model=model)
    answer = cab.ask("what's my sister's name?")
    assert answer.label is Label.KNOW and model.calls == []
    assert answer.route.reason == "drawer 1 already has the answer"


def test_safety_still_comes_before_drawer1():
    cab = build_cabinet()
    cab.store.add_fact("die", "Something filed about dying.")
    assert cab.ask("do i want to die?").route.crisis
