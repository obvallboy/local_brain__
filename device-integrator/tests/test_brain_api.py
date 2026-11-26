"""The Brain panel's API: the File Cabinet AI hosted inside the Device Integrator."""

import pytest

from app import create_app
from integrator.assistant import Assistant, AssistantConfig, import_filecabinet

SNAPSHOT = {
    "serial": [{"device": "COM3", "description": "USB-SERIAL CH340", "vid": "1a86", "pid": "7523"}],
    "usb": [{"vid": "046d", "pid": "c52b", "product": "USB Receiver", "bus": "1", "address": "4"}],
    "storage": [], "network": [],
}


@pytest.fixture
def client(tmp_path):
    fc = import_filecabinet()
    app_box = {}

    def labels():
        return app_box["app"].config["NOTES"].all()

    cabinet = fc.FileCabinet(store=fc.Store(str(tmp_path / "cabinet.db")),
                             devices=lambda: SNAPSHOT, labels=labels)
    assistant = Assistant(AssistantConfig(db_path=str(tmp_path / "cabinet.db")), cabinet_obj=cabinet)
    app = create_app(data_dir=str(tmp_path), assistant=assistant)
    app_box["app"] = app
    app.config["TESTING"] = True
    return app.test_client()


def ask(client, message):
    r = client.post("/api/brain/ask", json={"message": message})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def test_page_has_the_brain_panel(client):
    body = client.get("/").data
    assert b'id="brain"' in body and b"brain-toggle" in body


def test_status(client):
    s = client.get("/api/brain/status").get_json()
    assert s["ready"] is True
    assert s["model"] is None  # no model in tests: drawers and rules only
    assert s["memory_file"].endswith("cabinet.db")


def test_learns_and_answers(client):
    assert ask(client, "my brother's name is leo")["label"] == "Filed"
    r = ask(client, "what's my brother's name")
    assert r["label"] == "I know" and "leo" in r["text"]
    assert r["drawers"] == ["drawer1"]


def test_device_question_uses_discovery_and_your_labels(client):
    client.post("/api/notes", json={"key": "serial:COM3", "label": "Arduino Uno"})
    r = ask(client, "is my arduino plugged in?")
    assert r["label"] == "I checked"
    assert "Arduino Uno" in r["text"] and "COM3" in r["text"]
    assert r["route"]["kind"] == "devices"


def test_never_guesses_personal_facts(client):
    r = ask(client, "what was the name of my first dog?")
    assert r["label"] == "I'm not sure"


def test_slash_commands(client):
    assert "Commands:" in ask(client, "/help")["text"]
    assert ask(client, "/like blue | calm")["label"] == "Command"
    assert ask(client, "do you think blue is pretty?")["label"] == "I know"


def test_empty_and_oversized_messages_are_rejected(client):
    assert client.post("/api/brain/ask", json={"message": "  "}).status_code == 400
    assert client.post("/api/brain/ask", json={"message": "x" * 2001}).status_code == 400


def test_export_then_import(client, tmp_path):
    ask(client, "my sister lives in denver")
    exported = client.get("/api/brain/export")
    assert "attachment" in exported.headers["Content-Disposition"]
    data = exported.get_json()

    # A second machine with an empty memory.
    fc = import_filecabinet()
    other = Assistant(AssistantConfig(db_path=str(tmp_path / "other.db")),
                      cabinet_obj=fc.FileCabinet(store=fc.Store(str(tmp_path / "other.db")), seed_cases=False))
    other_client = create_app(data_dir=str(tmp_path / "other"), assistant=other).test_client()
    r = other_client.post("/api/brain/import", json=data)
    assert r.status_code == 200 and r.get_json()["added"]["facts"] >= 1
    assert ask(other_client, "where does my sister live")["label"] == "I know"


def test_import_rejects_garbage(client):
    assert client.post("/api/brain/import", data="not json", content_type="application/json").status_code == 400
    assert client.post("/api/brain/import", json={"hello": 1}).status_code == 400


def test_lazy_load_without_models(tmp_path):
    # No models folder: the Brain still works, on drawers and rules, and says why.
    assistant = Assistant(AssistantConfig(db_path=str(tmp_path / "c.db"), models_dir=str(tmp_path / "none")))
    client = create_app(data_dir=str(tmp_path), assistant=assistant).test_client()
    assert client.get("/api/brain/status").get_json()["ready"] is False
    assert ask(client, "my dog's name is biscuit")["label"] == "Filed"
    status = client.get("/api/brain/status").get_json()
    assert status["ready"] is True and status["model"] is None
    assert any("no model found" in n for n in status["notes"])
