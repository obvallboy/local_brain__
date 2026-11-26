"""The integration brain: thermostat control loop + data-integrity guard.

Transport-agnostic and pure stdlib, so it can be unit-tested without any of the
protocol libraries or hardware. This is the real version of the Device Bench's
"brain": it validates each reading, rejects corrupt data, holds the last good
value, and drives the PLC vent to keep the temperature in a band.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .anomaly import AnomalyDetector


def default_validate(value: Any) -> bool:
    """Plausibility check for a temperature reading (°C). Rejects non-numbers,
    NaN/inf, and physically impossible values like 999. The engine can swap this
    for the pydantic-backed validator in :mod:`integration.models`."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and -40.0 <= value <= 85.0
    )


@dataclass
class Command:
    device: str
    action: str
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BrainConfig:
    hi: float = 28.0          # open the vent at/above this
    lo: float = 24.0          # close the vent at/below this
    integrity: bool = True    # validate readings before acting (the range guard)
    validate: Callable[[Any], bool] = default_validate
    # optional learned guard: flags in-range-but-abnormal readings. None = off.
    detector: Optional[AnomalyDetector] = None


@dataclass
class Brain:
    cfg: BrainConfig = field(default_factory=BrainConfig)
    last_good: float = 22.0
    vent_open: bool = False
    alerts: List[Dict[str, Any]] = field(default_factory=list)
    rejected: int = 0
    anomalies: int = 0
    _integrity_alerted: bool = False
    _anomaly_alerted: bool = False

    # -- guards: integrity (range) then learned anomaly ------------------
    def ingest(self, raw_value: Any, ts: float | None = None) -> Tuple[bool, float]:
        """Validate a reading. Returns ``(accepted, value_used)``.

        Two guards run in order. (1) Integrity: a corrupt / out-of-range reading
        is rejected, an integrity alert is raised once, and ``last_good`` is held.
        (2) Learned anomaly (only if a detector is configured): a reading that
        passes the range check but is abnormal *for this sensor* is also rejected
        with an anomaly alert, so an in-range glitch can't drive the vent. A
        trusted reading updates ``last_good``."""
        ts = time.time() if ts is None else ts
        numeric = (
            isinstance(raw_value, (int, float))
            and not isinstance(raw_value, bool)
            and math.isfinite(raw_value)
        )
        # guard 1: integrity / plausible range
        if self.cfg.integrity and not self.cfg.validate(raw_value):
            self.rejected += 1
            if not self._integrity_alerted:
                self.alerts.append({"t": ts, "kind": "integrity",
                                    "msg": f"rejected reading {raw_value!r}; holding {self.last_good}"})
                self._integrity_alerted = True
            return False, self.last_good
        # guard 2: learned anomaly (sees only numeric, in-range readings)
        if self.cfg.detector is not None and numeric:
            is_anomaly, zscore = self.cfg.detector.check(float(raw_value))
            if is_anomaly:
                self.rejected += 1
                self.anomalies += 1
                if not self._anomaly_alerted:
                    self.alerts.append({"t": ts, "kind": "anomaly",
                                        "msg": f"in-range reading {raw_value} looks abnormal "
                                               f"(z={zscore:.1f}); holding {self.last_good}"})
                    self._anomaly_alerted = True
                return False, self.last_good
        if numeric:
            self.last_good = float(raw_value)
            self._integrity_alerted = False
            self._anomaly_alerted = False
            return True, self.last_good
        # guard off but value is not usable as a number: keep last_good
        return False, self.last_good

    # -- control logic (thermostat) --------------------------------------
    def decide(self) -> List[Command]:
        cmds: List[Command] = []
        if self.last_good >= self.cfg.hi and not self.vent_open:
            self.vent_open = True
            cmds.append(Command("plc-01", "write_register", {"register": 40001, "value": 1}))
        elif self.last_good <= self.cfg.lo and self.vent_open:
            self.vent_open = False
            cmds.append(Command("plc-01", "write_register", {"register": 40001, "value": 0}))
        return cmds

    def step(self, raw_value: Any, ts: float | None = None) -> List[Command]:
        self.ingest(raw_value, ts)
        return self.decide()

    def device_offline(self, name: str, ts: float | None = None) -> None:
        self.alerts.append({"t": time.time() if ts is None else ts,
                            "kind": "offline", "msg": f"{name} is offline"})
