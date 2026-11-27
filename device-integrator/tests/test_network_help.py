"""Live network scanning, exercised against a fake socket (no network)."""

import socket as real_socket

import pytest

import integrator.network_help as nh
from app import create_app
from integrator.assistant import Assistant, AssistantConfig, import_filecabinet


class FakeConn:
    def __init__(self, banner: bytes):
        self._banner = banner

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def settimeout(self, _):
        pass

    def sendall(self, _):
        pass

    def recv(self, _):
        return self._banner


@pytest.fixture
def fake_net(monkeypatch):
    # An ESP-like host: 80 and 3232 open, HTTP banner mentions ESP; everything else closed.
    open_ports = {80: b"HTTP/1.0 200 OK\r\nServer: ESP8266\r\n", 3232: b""}

    def create_connection(addr, timeout=None):
        host, port = addr
        if port in open_ports:
            return FakeConn(open_ports[port])
        raise OSError("closed")

    monkeypatch.setattr(nh.socket, "create_connection", create_connection)
    return open_ports


def test_scan_identifies_an_esp(fake_net):
    out = nh.scan("192.168.1.50")
    assert 80 in out["open_ports"] and 3232 in out["open_ports"]
    assert "ESP" in (out["guess"] or "")
    assert "192.168.1.50" in out["say"]


def test_scan_host_that_answers_nothing(monkeypatch):
    def refuse(addr, timeout=None):
        raise OSError("closed")
    monkeypatch.setattr(nh.socket, "create_connection", refuse)
    out = nh.scan("10.0.0.9")
    assert out["open_ports"] == [] and "didn't answer" in out["say"]


def test_endpoint(fake_net, tmp_path):
    import_filecabinet()
    import filecabinet as fc
    cab = fc.FileCabinet(store=fc.Store(str(tmp_path / "c.db")))
    app = create_app(data_dir=str(tmp_path),
                     assistant=Assistant(AssistantConfig(db_path=str(tmp_path / "c.db")), cabinet_obj=cab))
    client = app.test_client()
    r = client.get("/api/brain/net-scan?host=192.168.1.50")
    assert r.status_code == 200 and "ESP" in (r.get_json()["guess"] or "")
    assert client.get("/api/brain/net-scan").status_code == 400


def test_prober_is_safe_against_real_closed_ports():
    # A real probe to a closed local port returns (False, None), not an exception.
    probe = nh.tcp_prober(timeout=0.2)
    assert probe("127.0.0.1", 9) == (False, None)  # port 9 (discard) is virtually never open
    assert real_socket  # import kept
