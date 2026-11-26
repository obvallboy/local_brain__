"""Integration engine: wires a transport + the brain + validation into a loop.

Run it against the in-memory simulator (no hardware, no broker):

    python -m integration.engine --sim --ticks 24 --fuzz-after 8

To drive real devices, construct the real transports from
:mod:`integration.transports` and feed their readings to the same
:class:`~integration.brain.Brain`.
"""

from __future__ import annotations

import argparse
from typing import Any, Callable, Dict, List, Optional, Tuple

from .anomaly import AnomalyDetector
from .brain import Brain, BrainConfig, default_validate
from .transports import SimTransport


def build_validator() -> Callable[[Any], bool]:
    """Use the pydantic model as the validator when available; otherwise the
    brain's stdlib check. Both reject 999/NaN/out-of-range."""
    try:
        from .models import parse_reading

        def validate(value: Any) -> bool:
            return parse_reading({"device": "temp-01", "value": value, "ts": 0.0}) is not None

        return validate
    except Exception:
        return default_validate


def run_sim(ticks: int = 24, fuzz_after: Optional[int] = None,
            integrity: bool = True, anomaly: bool = True,
            anomaly_at: Optional[int] = None) -> Tuple[Brain, List[Dict[str, Any]]]:
    """Run the engine over the simulator and return (brain, per-tick log).

    ``fuzz_after`` injects out-of-range corrupt data (caught by the integrity
    guard); ``anomaly_at`` injects a single *in-range* glitch of 45 °C (passes the
    range check but is abnormal for this sensor — caught only by the learned
    anomaly guard when ``anomaly`` is on)."""
    t = SimTransport()
    detector = AnomalyDetector() if anomaly else None
    brain = Brain(BrainConfig(integrity=integrity, validate=build_validator(), detector=detector))
    log: List[Dict[str, Any]] = []
    for i in range(ticks):
        if fuzz_after is not None and i == fuzz_after:
            t.fuzz = True
        reading = t.read_sensor()
        if anomaly_at is not None and i == anomaly_at:
            reading = 45.0  # in range (-40..85) yet far from this sensor's normal band
        accepted, used = brain.ingest(reading)
        for cmd in brain.decide():
            if cmd.action == "write_register":
                t.write_register(cmd.args["register"], cmd.args["value"])
        log.append({"tick": i, "reading": reading, "used": used,
                    "accepted": accepted, "vent": t.vent})
    return brain, log


def main(argv: Optional[List[str]] = None) -> None:
    p = argparse.ArgumentParser(description="Device integration engine")
    p.add_argument("--sim", action="store_true", help="run against the in-memory simulator")
    p.add_argument("--ticks", type=int, default=24)
    p.add_argument("--fuzz-after", type=int, default=None, help="inject corrupt data after N ticks")
    p.add_argument("--anomaly-at", type=int, default=None,
                   help="inject one in-range (45°C) glitch at tick N — only the anomaly guard catches it")
    p.add_argument("--no-integrity", action="store_true", help="disable the data-integrity (range) guard")
    p.add_argument("--no-anomaly", action="store_true", help="disable the learned anomaly guard")
    args = p.parse_args(argv)

    if not args.sim:
        print("Standalone demo runs in --sim. For real devices, point the transports in\n"
              "integration.transports at your broker / PLC / camera and feed the brain.")
        return

    brain, log = run_sim(args.ticks, args.fuzz_after, integrity=not args.no_integrity,
                         anomaly=not args.no_anomaly, anomaly_at=args.anomaly_at)
    for e in log:
        mark = "" if e["accepted"] else "   << REJECTED (held last-good)"
        print(f"t{e['tick']:>2}  reading={str(e['reading']):>8}  used={e['used']:>5}°C  "
              f"vent={'OPEN' if e['vent'] else 'closed'}{mark}")
    print(f"\nrejected={brain.rejected}  (anomalies={brain.anomalies})  alerts={len(brain.alerts)}  "
          f"integrity={'OFF' if args.no_integrity else 'ON'}  "
          f"anomaly={'OFF' if args.no_anomaly else 'ON'}  "
          f"final_vent={'OPEN' if brain.vent_open else 'closed'}")
    for a in brain.alerts:
        print(f"  ! {a['kind']}: {a['msg']}")


if __name__ == "__main__":
    main()
