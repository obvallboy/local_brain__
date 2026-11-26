"""Transports: one in-memory simulator and three real-library adapters.

``SimTransport`` (pure stdlib) is the Device Bench "Lab network" fleet, so the
engine runs with no hardware. The real adapters wrap paho-mqtt / pymodbus /
requests and import their library lazily — point them at a real broker, PLC or
camera and the same engine drives real devices.
"""

from __future__ import annotations

import random
from typing import Any, Dict, Optional


class SimTransport:
    """In-memory mixed fleet (MQTT sensor + Modbus PLC + HTTP camera)."""

    def __init__(self, fuzz: bool = False):
        self.temp = 22.0
        self.vent = 0
        self.fuzz = fuzz
        self.online = {"temp-01": True, "plc-01": True, "cam-01": True}

    def read_sensor(self) -> Any:
        drift = -0.9 if self.vent == 1 else 0.8           # vent cools, closed heats
        self.temp = round(self.temp + drift + random.uniform(-0.15, 0.15), 1)
        if self.fuzz:
            return random.choice([999.0, float("nan"), -273.1, 1500.0, "0x8F3A"])
        return self.temp

    def write_register(self, register: int, value: int) -> bool:
        if register == 40001:
            self.vent = value
        return True

    def poll_camera(self) -> Dict[str, Any]:
        return {"online": self.online.get("cam-01", True), "res": "1920x1080"}


class MqttTransport:
    """Real MQTT telemetry via paho-mqtt (subscribe to the sensor topic)."""

    def __init__(self, host: str = "localhost", port: int = 1883, topic: str = "site/temp"):
        import paho.mqtt.client as mqtt  # lazy import

        self.host, self.port, self.topic = host, port, topic
        self._last: Optional[dict] = None
        self.client = mqtt.Client()
        self.client.on_message = self._on_message

    def _on_message(self, client, userdata, msg):  # pragma: no cover - needs a broker
        import json

        try:
            self._last = json.loads(msg.payload.decode())
        except Exception:
            self._last = None

    def connect(self):  # pragma: no cover - needs a broker
        self.client.connect(self.host, self.port)
        self.client.subscribe(self.topic)
        self.client.loop_start()

    def read_sensor(self):  # pragma: no cover - needs a broker
        return (self._last or {}).get("tempC")


class ModbusTransport:
    """Real Modbus/TCP via pymodbus. Register 40001 is the vent coil/holding reg."""

    def __init__(self, host: str = "localhost", port: int = 502, unit: int = 1):
        from pymodbus.client import ModbusTcpClient  # lazy import

        self.client = ModbusTcpClient(host, port=port)
        self.unit = unit

    def connect(self):  # pragma: no cover - needs a PLC
        return self.client.connect()

    def write_register(self, register: int, value: int):  # pragma: no cover
        return self.client.write_register(register - 40001, value, slave=self.unit)

    def read_register(self, register: int):  # pragma: no cover
        rr = self.client.read_holding_registers(register - 40001, 1, slave=self.unit)
        return rr.registers[0] if not rr.isError() else None


class HttpTransport:
    """Real HTTP/REST camera via requests."""

    def __init__(self, base: str = "http://camera.local"):
        import requests  # lazy import

        self._requests = requests
        self.base = base

    def poll_camera(self) -> Dict[str, Any]:  # pragma: no cover - needs a server
        r = self._requests.get(self.base + "/api/status", timeout=3)
        r.raise_for_status()
        return r.json()
