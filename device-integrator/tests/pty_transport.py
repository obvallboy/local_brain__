"""A PTY-backed Transport for exercising serial sessions without hardware.

The master side stands in for "the dev board": whatever the test writes to
the master appears as incoming data on the session, and whatever the session
writes shows up for the test to read on the master.
"""

import os
import select
import tty

from integrator.serialconsole import Transport


class PtyTransport(Transport):
    def __init__(self, port="pty", baudrate=115200, **kwargs):
        self.master, self.slave = os.openpty()
        # A real serial line is raw: no canonical line buffering and no
        # newline translation. A fresh PTY defaults to cooked mode, so put
        # both ends into raw mode to emulate a UART faithfully.
        for fd in (self.master, self.slave):
            try:
                tty.setraw(fd)
            except Exception:
                pass
        self._port = port
        self._baud = baudrate
        self._closed = False

    def read_available(self, max_bytes=4096):
        r, _, _ = select.select([self.slave], [], [], 0.1)
        if r:
            try:
                return os.read(self.slave, max_bytes)
            except OSError:
                return b""
        return b""

    def write(self, data):
        return os.write(self.slave, data)

    def close(self):
        if self._closed:
            return
        self._closed = True
        for fd in (self.slave, self.master):
            try:
                os.close(fd)
            except OSError:
                pass

    @property
    def description(self):
        return f"{self._port} @ {self._baud} baud (pty)"

    # -- test-side helpers (the "device" end) -----------------------------
    def device_send(self, data: bytes) -> int:
        """Simulate the device sending bytes to the host."""
        return os.write(self.master, data)

    def device_recv(self, timeout=0.5, max_bytes=4096) -> bytes:
        """Read what the host wrote toward the device."""
        r, _, _ = select.select([self.master], [], [], timeout)
        if r:
            return os.read(self.master, max_bytes)
        return b""
