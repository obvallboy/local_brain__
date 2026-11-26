import time

import pytest

from app import create_app
from integrator.serialconsole import SessionManager
from tests.pty_transport import PtyTransport


@pytest.fixture
def client(tmp_path):
    created = {}

    def factory(port, baudrate=115200, **kwargs):
        t = PtyTransport(port, baudrate=baudrate, **kwargs)
        created["last"] = t
        return t

    mgr = SessionManager(transport_factory=factory)
    app = create_app(data_dir=str(tmp_path), session_manager=mgr)
    app.config["TESTING"] = True
    client = app.test_client()
    client._created = created  # type: ignore[attr-defined]
    yield client
    mgr.close_all()


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"Device Integrator" in r.data


def test_devices_endpoint(client):
    r = client.get("/api/devices")
    assert r.status_code == 200
    body = r.get_json()
    assert set(body) >= {"capabilities", "serial", "usb", "storage", "network"}
    for p in body["serial"]:
        assert p["key"].startswith("serial:")


def test_notes_crud(client):
    r = client.post("/api/notes", json={"key": "usb:1:2", "note": "hi", "label": "L"})
    assert r.status_code == 200
    assert client.get("/api/notes").get_json()["usb:1:2"]["note"] == "hi"

    r = client.delete("/api/notes?key=usb:1:2")
    assert r.get_json()["deleted"] is True
    assert "usb:1:2" not in client.get("/api/notes").get_json()


def test_notes_requires_key(client):
    assert client.post("/api/notes", json={"note": "x"}).status_code == 400


def test_usb_detail_rejects_non_sys_path(client):
    r = client.get("/api/usb/detail?sysfs_path=/etc/passwd")
    assert r.status_code == 400


def test_serial_open_read_write_close(client):
    r = client.post("/api/serial/open", json={"port": "/dev/fake", "baud": 9600})
    assert r.status_code == 200
    sid = r.get_json()["id"]
    transport = client._created["last"]

    transport.device_send(b"boot ok\n")
    # Poll the read endpoint until data shows up.
    deadline = time.time() + 2
    chunks = []
    last = 0
    while time.time() < deadline and not chunks:
        body = client.get(f"/api/serial/{sid}/read?since={last}").get_json()
        chunks = body["chunks"]
        last = body["last_seq"]
        if not chunks:
            time.sleep(0.03)
    assert any("boot ok" in c["text"] for c in chunks)

    # Write with hex + newline.
    w = client.post(f"/api/serial/{sid}/write", json={"data": "41 42", "hex": True})
    assert w.get_json()["written"] == 2
    assert transport.device_recv() == b"AB"

    assert client.post(f"/api/serial/{sid}/close").get_json()["closed"] is True
    # Reading a closed/removed session is a 404.
    assert client.get(f"/api/serial/{sid}/read").status_code == 404


def test_serial_write_bad_hex(client):
    sid = client.post("/api/serial/open", json={"port": "/dev/fake"}).get_json()["id"]
    r = client.post(f"/api/serial/{sid}/write", json={"data": "zzzz", "hex": True})
    assert r.status_code == 400


def test_export_has_notes(client):
    client.post("/api/notes", json={"key": "k", "note": "n"})
    r = client.get("/api/export")
    assert r.status_code == 200
    assert "attachment" in r.headers.get("Content-Disposition", "")
    assert r.get_json()["notes"]["k"]["note"] == "n"
