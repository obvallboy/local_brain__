"""Pydantic models — the real data-integrity layer.

Validating a reading here is the production version of the Device Bench's
integrity guard: a 999 °C payload raises ``ValidationError`` instead of being
blindly acted on. Requires ``pydantic>=2``.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SensorReading(BaseModel):
    """A validated telemetry reading. ``value`` must be physically plausible."""

    model_config = ConfigDict(extra="forbid")

    device: str
    metric: str = "tempC"
    value: float = Field(ge=-40.0, le=85.0)  # 999 / NaN / -300 are rejected
    ts: float = 0.0


class DeviceConfig(BaseModel):
    """Typed description of a fleet device (what the engine connects to)."""

    name: str
    ip: str
    proto: str = Field(pattern=r"^(mqtt|modbus|http|gpio)$")
    topic: Optional[str] = None
    unit: int = 1


def parse_reading(payload: dict) -> Optional[SensorReading]:
    """Return a validated :class:`SensorReading`, or ``None`` if the payload is
    corrupt. Used by the engine as the brain's validator."""
    from pydantic import ValidationError

    try:
        return SensorReading(**payload)
    except ValidationError:
        return None
