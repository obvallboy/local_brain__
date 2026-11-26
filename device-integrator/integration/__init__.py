"""Real device-integration stack — the production counterpart to the Device Bench.

Everything you tested in the simulator (the mixed fleet, the thermostat control
loop, the data-integrity guard) runs here as real code against real transports:

    MQTT   — paho-mqtt        (sensor telemetry)
    Modbus — pymodbus         (PLC registers / the vent)
    HTTP   — requests         (IP camera / REST devices)
    GPIO   — RPi.GPIO         (physical pins, on a Raspberry Pi)
    models — pydantic         (the data-integrity validation)
    crypto — cryptography     (signed telemetry)

The transport-neutral logic (``brain``) is pure stdlib so it is testable without
any of those libraries or any hardware. The library-backed adapters import their
dependency lazily, so this package imports and the simulator runs anywhere.

Run the whole thing against the in-memory simulator (no hardware, no broker):

    python -m integration.engine --sim --ticks 24 --fuzz-after 8
"""

__all__ = ["brain", "models", "security", "transports", "gpio", "engine"]
__version__ = "0.1.0"
