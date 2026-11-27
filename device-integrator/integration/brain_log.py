"""Log the integration brain's alerts into the Brain's memory (the File Cabinet's episode log).

Then the Brain panel can answer "what went wrong with the sensor today?" from what really
happened. Alerts are written as episodes: place = the site, activity = "monitoring".
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, Iterable

DEFAULT_DB = os.path.join(
    os.environ.get("DEVICE_INTEGRATOR_DATA", os.path.join(os.path.expanduser("~"), ".device-integrator")),
    "cabinet.db",
)

_KIND_WORDS = {
    "integrity": "corrupt or impossible reading",
    "security": "forged or tampered message",
    "anomaly": "abnormal reading",
    "offline": "device offline",
}


def log_alerts_to_brain(alerts: Iterable[Dict[str, Any]], db_path: str = DEFAULT_DB,
                        device: str = "temp-01", place: str = "Lab network") -> int:
    """Write each alert as an episode. Returns how many were logged."""
    from integrator.assistant import import_filecabinet

    fc = import_filecabinet()
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    store = fc.Store(db_path)
    count = 0
    for alert in alerts:
        kind = alert.get("kind", "alert")
        details = f"Problem with the {device} sensor ({_KIND_WORDS.get(kind, kind)}): {alert.get('msg', '')}"
        ts = datetime.fromtimestamp(alert["t"]) if alert.get("t") else None
        store.log_episode(place, "monitoring", details, ts=ts)
        count += 1
    store.db.close()
    return count
