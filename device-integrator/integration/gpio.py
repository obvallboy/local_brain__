"""Physical pin control with RPi.GPIO — functional only on a Raspberry Pi.

Off a Pi (CI, a laptop) ``RPi.GPIO`` isn't importable, so this degrades to a
no-op and the engine still imports and runs. On a Pi, ``VentPin`` drives a real
output pin from the brain's vent decision.
"""

from __future__ import annotations

try:
    import RPi.GPIO as GPIO  # type: ignore

    AVAILABLE = True
except Exception:  # not on a Pi, or library missing
    GPIO = None
    AVAILABLE = False


class VentPin:
    def __init__(self, pin: int = 17):
        self.pin = pin
        if AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(pin, GPIO.OUT)

    def set(self, open_: bool) -> bool:
        if AVAILABLE:
            GPIO.output(self.pin, GPIO.HIGH if open_ else GPIO.LOW)
        return open_

    def cleanup(self) -> None:
        if AVAILABLE:
            GPIO.cleanup(self.pin)
