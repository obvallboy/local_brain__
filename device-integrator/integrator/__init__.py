"""Device Integrator — a local workbench for inspecting and tinkering with
hardware you own.

The package is intentionally dependency-light: the optional libraries
(``pyserial``, ``pyusb``, ``psutil``) are imported lazily so the app still
starts and reports useful information when they are absent. Nothing here
transmits, injects input, or reaches the network — it only reads/inspects
locally attached devices and talks to serial ports you explicitly open.
"""

__all__ = ["discovery", "serialconsole", "details", "notes"]

__version__ = "0.1.0"
