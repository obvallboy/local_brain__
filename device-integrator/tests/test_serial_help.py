"""Live serial scanning, exercised against a fake pyserial (no hardware)."""

import sys
import types

import pytest

import integrator.serial_help as sh
from app import create_app
from integrator.assistant import Assistant, AssistantConfig, import_filecabinet


class FakeSerial:
    """Stands in for serial.Serial: returns canned bytes regardless of baud."""

    payload = b"MicroPython v1.24.1 on 2024-11-29; Raspberry Pi Pico\r\n>>> "

    def __init__(self, port, baud, timeout=None):
        self.port, self.baud = port, baud

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def write(self, data):
        return len(data)

    def read(self, n):
        return self.payload


@pytest.fixture
def fake_pyserial(monkeypatch):
    fake = types.ModuleType("serial")
    fake.Serial = FakeSerial
    monkeypatch.setitem(sys.modules, "serial", fake)
    return fake


def test_scan_finds_baud_and_recognizes_micropython(fake_pyserial):
    out = sh.scan("/dev/ttyACM0")
    assert out["baud"] == 115200
    assert "MicroPython" in out["what"]
    assert "MicroPython" in out["say"]


def test_scan_reports_when_nothing_readable(fake_pyserial, monkeypatch):
    monkeypatch.setattr(FakeSerial, "payload", bytes([0xFF, 0x00, 0x80, 0xC1]))
    out = sh.scan("/dev/ttyACM0")
    assert out["baud"] is None
    assert "couldn't get readable text" in out["say"]


def test_scan_without_pyserial_says_so(monkeypatch):
    monkeypatch.setitem(sys.modules, "serial", None)  # import serial -> ImportError
    out = sh.scan("/dev/ttyACM0")
    assert "need pyserial" in out["say"]


def test_endpoint(fake_pyserial, tmp_path):
    import_filecabinet()
    import filecabinet as fc
    cab = fc.FileCabinet(store=fc.Store(str(tmp_path / "c.db")))
    app = create_app(data_dir=str(tmp_path),
                     assistant=Assistant(AssistantConfig(db_path=str(tmp_path / "c.db")), cabinet_obj=cab))
    client = app.test_client()
    r = client.get("/api/brain/serial-scan?port=/dev/ttyACM0")
    assert r.status_code == 200 and "MicroPython" in r.get_json()["say"]
    assert client.get("/api/brain/serial-scan").status_code == 400


def test_page_shows_devy_not_brain(tmp_path):
    import_filecabinet()
    import filecabinet as fc
    cab = fc.FileCabinet(store=fc.Store(str(tmp_path / "c.db")))
    app = create_app(data_dir=str(tmp_path),
                     assistant=Assistant(AssistantConfig(db_path=str(tmp_path / "c.db")), cabinet_obj=cab))
    body = app.test_client().get("/").data
    assert b"\xf0\x9f\xa7\xa0 Devy" in body  # the 🧠 Devy heading/button
