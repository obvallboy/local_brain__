"""Live serial scanning for Devy: open a real port, find its baud, recognize it.

Uses the File Cabinet's serialscan logic with a pyserial-backed reader. Reading a real
port needs hardware, so this is verified here only against a fake serial; live checking
happens with a board attached.
"""

from __future__ import annotations

from integrator.assistant import import_filecabinet


def make_reader(port: str, seconds: float = 1.2, nudge: bytes = b"\r\n"):
    """Return a reader(baud) -> bytes that opens `port` at that baud and reads a sample.

    It sends a newline first, which nudges a quiet REPL or bootloader into printing a
    prompt. Harmless on a console; it's your own hardware."""
    import serial  # pyserial; raises ImportError if not installed

    def read(baud: int) -> bytes:
        try:
            with serial.Serial(port, baud, timeout=seconds) as ser:
                if nudge:
                    try:
                        ser.write(nudge)
                    except Exception:
                        pass
                return ser.read(4096)
        except Exception:
            return b""

    return read


def scan(port: str, seconds: float = 1.2) -> dict:
    """Scan a port and return {baud, what, next_step, sample, say}. 'say' is Devy's summary."""
    import_filecabinet()
    from filecabinet.serialscan import detect_baud, recognize, report

    try:
        reader = make_reader(port, seconds)
    except ImportError:
        return {"say": "I need pyserial to read a serial port — install it with: pip install pyserial.",
                "baud": None, "what": None, "next_step": None, "sample": ""}
    result = detect_baud(reader)
    reading = recognize(result.sample) if result else None
    return {
        "baud": result.baud if result else None,
        "what": reading.what if reading else None,
        "next_step": reading.next_step if reading else None,
        "sample": result.sample if result else "",
        "say": report(result, reading),
    }
