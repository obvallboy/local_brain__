import time

import pytest

from integrator.serialconsole import SessionManager, decode_preview
from tests.pty_transport import PtyTransport


def _wait_for(predicate, timeout=2.0, interval=0.02):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


@pytest.fixture
def manager():
    # Keep a handle to the last transport so tests can act as the device.
    created = {}

    def factory(port, baudrate=115200, **kwargs):
        t = PtyTransport(port, baudrate=baudrate, **kwargs)
        created["last"] = t
        return t

    mgr = SessionManager(transport_factory=factory)
    mgr._created = created  # type: ignore[attr-defined]
    yield mgr
    mgr.close_all()


def test_open_and_read_incoming(manager):
    session = manager.open("/dev/fake", baudrate=9600)
    transport = manager._created["last"]

    transport.device_send(b"hello board\n")
    assert _wait_for(lambda: session.read_since(0)["chunks"])

    result = session.read_since(0)
    text = "".join(c["text"] for c in result["chunks"])
    assert "hello board" in text
    assert result["last_seq"] >= 1
    assert result["closed"] is False


def test_incremental_sequence(manager):
    session = manager.open("/dev/fake")
    transport = manager._created["last"]

    transport.device_send(b"first ")
    assert _wait_for(lambda: session.read_since(0)["chunks"])
    first = session.read_since(0)
    seq_after_first = first["last_seq"]

    # Reading again from the new cursor returns nothing new yet.
    assert session.read_since(seq_after_first)["chunks"] == []

    transport.device_send(b"second")
    assert _wait_for(lambda: session.read_since(seq_after_first)["chunks"])
    second = session.read_since(seq_after_first)
    text = "".join(c["text"] for c in second["chunks"])
    assert "second" in text
    assert "first" not in text  # not re-delivered


def test_write_reaches_device_with_line_ending(manager):
    session = manager.open("/dev/fake")
    transport = manager._created["last"]

    session.write(b"AT", line_ending="crlf")
    got = transport.device_recv()
    assert got == b"AT\r\n"
    assert session.info()["bytes_out"] == 4


def test_write_hex_bytes(manager):
    session = manager.open("/dev/fake")
    transport = manager._created["last"]

    session.write(bytes.fromhex("deadbeef"), line_ending="none")
    assert transport.device_recv() == b"\xde\xad\xbe\xef"


def test_close_marks_session_closed(manager):
    session = manager.open("/dev/fake")
    sid = session.id
    assert manager.get(sid) is session

    assert manager.close(sid) is True
    assert manager.get(sid) is None
    assert session.is_open is False
    # Closing an unknown session is a no-op.
    assert manager.close("nope") is False


def test_write_after_close_raises(manager):
    session = manager.open("/dev/fake")
    session.close()
    with pytest.raises(RuntimeError):
        session.write(b"x")


def test_decode_preview_is_lossy_not_crashing():
    assert decode_preview(b"\xff\xfe ok") .endswith("ok")


def test_buffer_is_bounded(manager):
    session = manager.open("/dev/fake")
    # maxlen defaults high; shrink via direct access for the test.
    session._buffer = type(session._buffer)(maxlen=3)
    transport = manager._created["last"]
    for i in range(10):
        transport.device_send(f"{i}".encode())
        time.sleep(0.02)
    _wait_for(lambda: len(session._buffer) == 3)
    assert len(session._buffer) <= 3
