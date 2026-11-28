"""Run MicroPython on a plugged-in board, with your approval: the "I ran it" half of Devy.

A model can *think* a program is right; only the board can say it *ran*. This sends a
snippet to a MicroPython board over USB with mpremote, runs it in the board's RAM (nothing
is saved to the board's flash), and returns exactly what the board printed.

Changing the real world needs your yes, so running is two steps:
  plan(port, code) -> shows the exact command and code, and returns a one-time token
  run_plan(token)  -> runs that exact code on that exact port, once
A token expires after a few minutes and can't be reused or pointed at different code.
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from integrator.assistant import import_filecabinet

MAX_CODE = 20_000
PLAN_TTL = 300.0          # seconds a reviewed plan stays valid
DEFAULT_TIMEOUT = 30.0    # seconds a snippet may run before mpremote is stopped
SNIPPET_NAME = "devy_snippet.py"

# Only real USB serial ports: never the empty ttyS placeholders, never arbitrary paths.
PORT_RE = re.compile(
    r"^(/dev/(ttyACM\d+|ttyUSB\d+|serial/by-id/[\w.:+@-]+|cu\.[\w.-]+|tty\.usb[\w.-]+)|COM\d+)$")

# Runs an argv list and returns a CompletedProcess. Injected so tests need no board.
Exec = Callable[..., subprocess.CompletedProcess]


def mpremote_path() -> Optional[str]:
    """mpremote next to the running Python (the app's venv) first, then PATH."""
    local = os.path.join(os.path.dirname(sys.executable), "mpremote")
    return local if os.access(local, os.X_OK) else shutil.which("mpremote")


def status(exec_: Exec = subprocess.run) -> Dict[str, Any]:
    exe = mpremote_path()
    if not exe:
        return {"installed": False, "hint": "pip install mpremote (in the app's .venv)"}
    try:
        out = exec_([exe, "--version"], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        out = ""
    return {"installed": True, "path": exe, "version": out}


def _identify(vid: str, pid: str, product: str) -> Optional[str]:
    try:
        import_filecabinet()
        from filecabinet.boards import identify
        info = identify(vid, pid, product)
        return info.name if info else None
    except Exception:
        return None


def list_boards(exec_: Exec = subprocess.run) -> List[Dict[str, Any]]:
    """USB serial devices that could be a MicroPython board (`mpremote connect list`),
    without the empty built-in ports."""
    exe = mpremote_path()
    if not exe:
        return []
    try:
        p = exec_([exe, "connect", "list"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return []
    boards = []
    for line in (p.stdout or "").splitlines():
        parts = line.split(None, 4)
        if len(parts) < 3:
            continue
        port, serial, vidpid = parts[:3]
        manufacturer = parts[3] if len(parts) > 3 and parts[3] != "None" else None
        product = parts[4] if len(parts) > 4 and parts[4] != "None" else None
        vid, _, pid = vidpid.partition(":")
        if vidpid in ("0000:0000", "None") or not PORT_RE.match(port):
            continue
        boards.append({
            "port": port, "vid": vid, "pid": pid,
            "serial_number": None if serial == "None" else serial,
            "manufacturer": manufacturer, "product": product,
            "board": _identify(vid, pid, product or ""),
        })
    return boards


def display_command(port: str) -> str:
    return f"mpremote connect {port} run {SNIPPET_NAME}"


def validate(port: str, code: str) -> None:
    if not PORT_RE.match(port or ""):
        raise ValueError("pick a USB serial port like /dev/ttyACM0 (built-in ttyS ports can't run MicroPython)")
    if not (code or "").strip():
        raise ValueError("there's no code to run")
    if len(code) > MAX_CODE:
        raise ValueError(f"that's too much code ({MAX_CODE} characters max)")


def run(port: str, code: str, timeout: float = DEFAULT_TIMEOUT, exec_: Exec = subprocess.run) -> Dict[str, Any]:
    """Run `code` on the board at `port` and report exactly what happened."""
    validate(port, code)
    exe = mpremote_path()
    command = display_command(port)
    if not exe:
        return {"ok": False, "ran": False, "label": "I'm not sure", "command": command, "stdout": "",
                "stderr": "", "say": "mpremote isn't installed, so I can't talk to the board. "
                                     "Install it with: pip install mpremote"}
    fd, path = tempfile.mkstemp(prefix="devy_", suffix=".py")
    started = time.monotonic()
    try:
        with os.fdopen(fd, "w") as f:
            f.write(code)
        try:
            p = exec_([exe, "connect", port, "run", path], capture_output=True, text=True, timeout=timeout)
            out, err, code_rc, timed_out = p.stdout or "", p.stderr or "", p.returncode, False
        except subprocess.TimeoutExpired as exc:
            dec = lambda b: b.decode(errors="replace") if isinstance(b, bytes) else (b or "")
            out, err, code_rc, timed_out = dec(exc.stdout), dec(exc.stderr), None, True
    finally:
        os.unlink(path)
    seconds = round(time.monotonic() - started, 2)

    traceback = "Traceback (most recent call last)" in out or "Traceback (most recent call last)" in err
    ok = code_rc == 0 and not traceback and not timed_out
    if ok:
        say = "I ran it on the board and it finished cleanly."
    elif timed_out:
        say = (f"I stopped waiting after {timeout:.0f} s. If the code loops forever it may still be running "
               "on the board. Unplug and replug it (or press its reset button) to stop it.")
    elif traceback:
        say = "I ran it on the board and it raised an error. The board's traceback is below."
    else:
        say = _connect_trouble(port, out + err)
    return {"ok": ok, "ran": code_rc is not None or timed_out, "label": "I ran it" if ok else
            ("I ran it" if traceback else "I'm not sure"), "command": command, "port": port,
            "stdout": out, "stderr": err, "returncode": code_rc, "seconds": seconds,
            "timed_out": timed_out, "say": say}


def _connect_trouble(port: str, text: str) -> str:
    """Plain-language reason a run never reached MicroPython."""
    low = text.lower()
    if "permission denied" in low or (os.path.exists(port) and not os.access(port, os.R_OK | os.W_OK)):
        return (f"I don't have permission to open {port}. On Arch/CachyOS, serial ports belong to the "
                "'uucp' group: run  sudo usermod -aG uucp $USER  then log out and back in (and restart Devy).")
    if not os.path.exists(port):
        return f"There's no board on {port} right now. Is it plugged in? Tap ↻ to look again."
    if "in use" in low or "busy" in low or "failed to access" in low:
        return (f"{port} is busy. Close anything else using it (Thonny, a serial console, the Console tab) "
                "and try again.")
    return ("I couldn't run it. The board didn't answer like MicroPython. Check it's flashed with "
            "MicroPython and that nothing else has the port open.")


class Planner:
    """Holds reviewed plans so that only code you've seen can run, once."""

    def __init__(self, ttl: float = PLAN_TTL, clock: Callable[[], float] = time.monotonic):
        self.ttl, self.clock = ttl, clock
        self._plans: Dict[str, tuple] = {}
        self._lock = threading.Lock()

    def plan(self, port: str, code: str) -> Dict[str, Any]:
        validate(port, code)
        token = secrets.token_urlsafe(18)
        now = self.clock()
        with self._lock:
            self._plans = {t: v for t, v in self._plans.items() if now - v[2] < self.ttl}
            self._plans[token] = (port, code, now)
        return {"token": token, "port": port, "code": code, "command": display_command(port),
                "expires_in": int(self.ttl),
                "say": "Here's exactly what will run on the board, in its RAM only (nothing is saved to it). "
                       "Approve to run it once."}

    def take(self, token: str) -> tuple:
        """Return (port, code) for a valid plan and use it up. KeyError if unknown or expired."""
        with self._lock:
            entry = self._plans.pop(token or "", None)
        if entry is None or self.clock() - entry[2] >= self.ttl:
            raise KeyError("that plan has expired or was already run. Review the code again")
        return entry[0], entry[1]
