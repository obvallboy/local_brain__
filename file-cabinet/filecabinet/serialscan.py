"""Serial console helper: find a board's baud rate and recognize what's answering.

Two jobs, both offline and honest:

1. detect_baud — try the common speeds, read a sample at each, and keep the one that
   produces readable text. If nothing is readable at any speed, say so; don't guess.
2. recognize — look at the text coming out and name what's talking (a MicroPython
   prompt, a Linux login, U-Boot, an ESP boot log, a GPS, ...), with a plain next step.
   Unrecognized output is reported as unrecognized.

Reading bytes from the port is injected (a callable baud -> bytes), so this is testable
without hardware; the Device Integrator supplies a pyserial-backed reader on a real port.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

# Ordered by how common they are, so a confident early hit can stop the search.
COMMON_BAUDS = (115200, 9600, 74880, 57600, 38400, 19200, 230400, 460800, 921600, 4800)

# A byte is "readable" if it is printable ASCII or ordinary whitespace.
_READABLE = set(range(0x20, 0x7F)) | {0x09, 0x0A, 0x0D}

Reader = Callable[[int], bytes]


def readability(data: bytes) -> float:
    """Fraction of bytes that look like normal text, 0..1. Empty data scores 0."""
    if not data:
        return 0.0
    return sum(b in _READABLE for b in data) / len(data)


@dataclass(frozen=True)
class BaudResult:
    baud: int
    sample: str
    score: float


def detect_baud(reader: Reader, bauds=COMMON_BAUDS, threshold: float = 0.75,
                good_enough: float = 0.95) -> Optional[BaudResult]:
    """Return the most readable baud above `threshold`, or None if none qualify.

    Stops early at the first baud scoring `good_enough` so a clear hit is fast."""
    best: Optional[BaudResult] = None
    for baud in bauds:
        data = reader(baud) or b""
        score = readability(data)
        text = data.decode("ascii", errors="replace")
        if best is None or score > best.score:
            best = BaudResult(baud, text, score)
        if score >= good_enough:
            return best
    return best if best and best.score >= threshold else None


@dataclass(frozen=True)
class Reading:
    what: str          # what's answering, e.g. "a MicroPython REPL"
    next_step: str     # a plain-language suggestion


# Each: (name, compiled pattern, next step). First match wins, so put the specific ones first.
_SIGNATURES = [
    ("CircuitPython", re.compile(r"Adafruit CircuitPython|CircuitPython \d", re.I),
     "Type Python at the >>> prompt, or drop a .py onto the CIRCUITPY drive. Tools: Mu, Thonny."),
    ("a MicroPython REPL", re.compile(r"MicroPython v|>>>\s*$|Traceback \(most recent", re.M),
     "Type Python at the >>> prompt. Tools: Thonny, mpremote. Ctrl-D soft-reboots, Ctrl-C stops a program."),
    ("an ESP32/ESP8266 boot log", re.compile(r"ets [A-Z][a-z]{2} +\d|rst:0x|boot:0x|cause:\d|ESP-ROM", re.I),
     "An Espressif chip booting. Its boot ROM often logs at 74880 baud; the app usually runs at 115200. Flash with esptool."),
    ("U-Boot (a bootloader)", re.compile(r"U-Boot \d|Hit any key to stop autoboot|^=>\s*$", re.M),
     "Press a key to stop autoboot, then 'help' lists commands. 'printenv' shows the settings."),
    ("a Linux login prompt", re.compile(r"\blogin:\s*$|localhost login:", re.M),
     "It wants a username and password. If you don't have them, a bootloader (single-user mode) may get you in."),
    ("a Linux shell", re.compile(r"root@[\w-]+:|[\w-]+@[\w-]+:[~/][^\n]*[#$]\s*$", re.M),
     "You're at a shell. 'uname -a' and 'cat /etc/os-release' tell you what it is."),
    ("a GPS (NMEA sentences)", re.compile(r"\$G[PNLA][A-Z]{3},"),
     "It's a GPS streaming NMEA sentences at (usually) 9600 baud. Each $GP... line is a position/time fix."),
    ("an AT-command modem", re.compile(r"\bOK\r?\n|\bRING\b|\+CME ERROR|\bAT\+", re.M),
     "Send 'AT' and it should answer 'OK'. 'ATI' identifies it."),
    ("a bootloader / firmware banner", re.compile(r"bootloader|Bootloader|boot>|Starting kernel|Uncompressing", re.M),
     "Early boot output. Watch for a prompt or a 'press key' message to interrupt it."),
]


def recognize(sample: str) -> Optional[Reading]:
    """Name what's answering on the serial line, or None if it isn't recognized."""
    if not sample or not sample.strip():
        return None
    for name, pattern, step in _SIGNATURES:
        if pattern.search(sample):
            return Reading(name, step)
    return None


def report(result: Optional[BaudResult], reading: Optional[Reading]) -> str:
    """A plain-language summary for Devy to say after a scan."""
    if result is None:
        return ("I couldn't get readable text at any common baud rate. Check the TX/RX wiring (they may be "
                "swapped), the ground, and that the board is powered and actually sending something.")
    head = f"I checked: readable text at {result.baud} baud."
    if reading:
        return f"{head} It looks like {reading.what}. {reading.next_step}"
    snippet = " ".join(result.sample.split())[:80]
    return f"{head} I don't recognize what it is from the output. First bytes: \"{snippet}\"."
