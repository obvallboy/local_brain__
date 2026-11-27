"""The serial console helper: find the baud rate and recognize what's answering."""

import pytest

from filecabinet.serialscan import detect_baud, readability, recognize, report


def test_readability_scoring():
    assert readability(b"MicroPython v1.24 on 2024\r\n>>> ") > 0.95
    assert readability(bytes([0x00, 0xFF, 0x80, 0x81, 0x00])) < 0.3
    assert readability(b"") == 0.0


def test_detect_baud_picks_the_readable_speed():
    # Garbage at every speed except 115200, where real text appears.
    def reader(baud):
        return b"MicroPython v1.24\r\n>>> " if baud == 115200 else bytes([0x00, 0xFF, 0xC3, 0x81])
    result = detect_baud(reader)
    assert result is not None and result.baud == 115200
    assert ">>>" in result.sample


def test_detect_baud_returns_none_when_nothing_is_readable():
    assert detect_baud(lambda b: bytes([0xFF, 0x00, 0x80, 0xC1])) is None


def test_detect_baud_stops_early_on_a_clear_hit():
    seen = []
    def reader(baud):
        seen.append(baud)
        return b"clean readable text at any speed here\r\n"  # 115200 is tried first
    detect_baud(reader)
    assert seen == [115200]  # didn't keep scanning once it had a clear hit


@pytest.mark.parametrize("sample, expect", [
    ("MicroPython v1.24.1 on 2024-11-29; Raspberry Pi Pico\r\n>>> ", "MicroPython"),
    ("Adafruit CircuitPython 9.0.0\r\n>>> ", "CircuitPython"),
    ("U-Boot 2021.01 (Jan 01 2021)\r\nHit any key to stop autoboot:  2", "U-Boot"),
    ("\r\nraspberrypi login: ", "login"),
    ("root@openwrt:/# ", "shell"),
    ("$GPGGA,123519,4807.038,N,01131.000,E,1,08\r\n", "GPS"),
    ("ets Jun  8 2016 00:22:57\r\nrst:0x1 (POWERON_RESET),boot:0x13", "ESP32"),
])
def test_recognize_known_consoles(sample, expect):
    reading = recognize(sample)
    assert reading is not None and expect.lower() in reading.what.lower()
    assert reading.next_step  # always offers a next step


def test_recognize_is_honest_about_the_unknown():
    assert recognize("x7#q2 random noise 9f3k") is None
    assert recognize("") is None


def test_report_wording():
    class B:  # minimal stand-in for BaudResult
        baud, sample, score = 9600, "$GPGGA,...", 0.99
    assert "9600 baud" in report(B(), recognize("$GPGGA,123519,4807.0,N"))
    assert "couldn't get readable text" in report(None, None)
    unknown = report(B(), None)
    assert "don't recognize" in unknown
