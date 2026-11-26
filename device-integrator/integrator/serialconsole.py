"""Serial console sessions.

Opening a serial port to a dev board (Arduino, ESP, STM32, a UART debug
header…) and exchanging bytes with it is the core "tinker" loop for
reverse-engineering your own hardware. This module manages those sessions:
each one runs a background reader thread that collects incoming bytes into a
bounded, sequence-numbered buffer, so the browser can poll incrementally.

The port I/O is abstracted behind a small ``Transport`` protocol. In normal
use the transport is a pyserial connection; in tests it is backed by a PTY,
so the whole session lifecycle can be exercised without physical hardware.
"""

from __future__ import annotations

import itertools
import threading
import time
import uuid
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple


# --------------------------------------------------------------------------
# Transport abstraction
# --------------------------------------------------------------------------
class Transport:
    """Minimal duplex byte transport used by a :class:`SerialSession`."""

    def read_available(self, max_bytes: int = 4096) -> bytes:
        """Return up to ``max_bytes`` of incoming data. May block briefly;
        returns ``b""`` if nothing arrived within that window."""
        raise NotImplementedError

    def write(self, data: bytes) -> int:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    @property
    def description(self) -> str:
        return "transport"


class SerialTransport(Transport):
    """pyserial-backed transport. Imported lazily so the module loads even
    where pyserial is not installed."""

    def __init__(self, port: str, baudrate: int = 115200, **kwargs: Any):
        import serial  # type: ignore

        read_timeout = kwargs.pop("read_timeout", 0.1)
        self._ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=read_timeout,
            write_timeout=kwargs.pop("write_timeout", 2.0),
            bytesize=kwargs.pop("bytesize", serial.EIGHTBITS),
            parity=kwargs.pop("parity", serial.PARITY_NONE),
            stopbits=kwargs.pop("stopbits", serial.STOPBITS_ONE),
        )
        self._port = port
        self._baud = baudrate

    def read_available(self, max_bytes: int = 4096) -> bytes:
        waiting = 0
        try:
            waiting = self._ser.in_waiting
        except Exception:
            waiting = 0
        if waiting:
            return self._ser.read(min(waiting, max_bytes))
        # Block up to the configured read timeout for at least one byte so the
        # reader thread does not spin.
        return self._ser.read(1)

    def write(self, data: bytes) -> int:
        return self._ser.write(data) or 0

    def close(self) -> None:
        try:
            self._ser.close()
        except Exception:
            pass

    @property
    def description(self) -> str:
        return f"{self._port} @ {self._baud} baud"


# --------------------------------------------------------------------------
# Session
# --------------------------------------------------------------------------
_LINE_ENDINGS = {"none": b"", "lf": b"\n", "cr": b"\r", "crlf": b"\r\n"}


def decode_preview(data: bytes) -> str:
    """Human-readable text view of raw bytes (UTF-8, lossy)."""
    return data.decode("utf-8", errors="replace")


class SerialSession:
    """A single open serial connection with a background reader."""

    def __init__(
        self,
        transport: Transport,
        session_id: Optional[str] = None,
        buffer_chunks: int = 4000,
        label: Optional[str] = None,
    ):
        self.id = session_id or uuid.uuid4().hex[:12]
        self.label = label or transport.description
        self._transport = transport
        self._buffer: Deque[Tuple[int, float, bytes]] = deque(maxlen=buffer_chunks)
        self._seq = itertools.count(1)
        self._last_seq = 0
        self._lock = threading.Lock()
        self._running = threading.Event()
        self._running.set()
        self.error: Optional[str] = None
        self.opened_at = time.time()
        self.bytes_in = 0
        self.bytes_out = 0
        self._thread = threading.Thread(
            target=self._reader_loop, name=f"serial-{self.id}", daemon=True
        )
        self._thread.start()

    # -- reader thread ----------------------------------------------------
    def _reader_loop(self) -> None:
        while self._running.is_set():
            try:
                data = self._transport.read_available()
            except Exception as exc:  # pragma: no cover - hardware dependent
                self.error = f"read error: {exc}"
                self._running.clear()
                break
            if data:
                seq = next(self._seq)
                with self._lock:
                    self._buffer.append((seq, time.time(), data))
                    self._last_seq = seq
                    self.bytes_in += len(data)

    # -- public API -------------------------------------------------------
    @property
    def is_open(self) -> bool:
        return self._running.is_set()

    def write(self, data: bytes, line_ending: str = "none") -> int:
        if not self._running.is_set():
            raise RuntimeError("session is closed")
        payload = data + _LINE_ENDINGS.get(line_ending, b"")
        n = self._transport.write(payload)
        with self._lock:
            self.bytes_out += n
        return n

    def read_since(self, since_seq: int = 0, max_chunks: int = 1000) -> Dict[str, Any]:
        """Return buffered chunks with ``seq > since_seq`` (oldest first)."""
        with self._lock:
            chunks = [c for c in self._buffer if c[0] > since_seq][:max_chunks]
            last = self._last_seq
        return {
            "chunks": [
                {
                    "seq": seq,
                    "t": t,
                    "text": decode_preview(data),
                    "hex": data.hex(),
                    "len": len(data),
                }
                for (seq, t, data) in chunks
            ],
            "last_seq": last,
            "closed": not self._running.is_set(),
            "error": self.error,
        }

    def close(self) -> None:
        self._running.clear()
        self._thread.join(timeout=1.0)
        self._transport.close()

    def info(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "open": self.is_open,
            "opened_at": self.opened_at,
            "uptime_s": round(time.time() - self.opened_at, 1),
            "bytes_in": self.bytes_in,
            "bytes_out": self.bytes_out,
            "last_seq": self._last_seq,
            "error": self.error,
        }


# --------------------------------------------------------------------------
# Manager
# --------------------------------------------------------------------------
class SessionManager:
    """Owns all open serial sessions, keyed by session id."""

    def __init__(self, transport_factory: Optional[Callable[..., Transport]] = None):
        # Injectable so tests can substitute a PTY-backed transport.
        self._factory = transport_factory or SerialTransport
        self._sessions: Dict[str, SerialSession] = {}
        self._lock = threading.Lock()

    def open(self, port: str, baudrate: int = 115200, label: Optional[str] = None,
             **kwargs: Any) -> SerialSession:
        transport = self._factory(port, baudrate=baudrate, **kwargs)
        session = SerialSession(transport, label=label or f"{port} @ {baudrate}")
        with self._lock:
            self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Optional[SerialSession]:
        with self._lock:
            return self._sessions.get(session_id)

    def close(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        session.close()
        return True

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            sessions = list(self._sessions.values())
        return [s.info() for s in sessions]

    def close_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for s in sessions:
            s.close()
