"""Per-device notes and labels.

When you reverse-engineer hardware you accumulate findings — which pins are
what, the baud rate that worked, the meaning of a status byte. This stores a
free-text note and a friendly label per device, keyed by a stable device key
(USB vid:pid:serial, or a serial port path). Persistence is a single JSON
file, guarded by a lock so the web handlers can write concurrently.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, Optional


class NotesStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._data: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                self._data = loaded
        except FileNotFoundError:
            self._data = {}
        except Exception:
            # Corrupt file: keep a backup, start fresh rather than crash.
            try:
                os.replace(self.path, self.path + ".corrupt")
            except Exception:
                pass
            self._data = {}

    def _flush(self) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2, sort_keys=True)
        os.replace(tmp, self.path)

    # -- API --------------------------------------------------------------
    def get(self, key: str) -> Dict[str, Any]:
        with self._lock:
            return dict(self._data.get(key, {}))

    def all(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return json.loads(json.dumps(self._data))  # deep copy

    def set(self, key: str, note: Optional[str] = None,
            label: Optional[str] = None) -> Dict[str, Any]:
        if not key:
            raise ValueError("key is required")
        with self._lock:
            entry = self._data.get(key, {})
            if note is not None:
                entry["note"] = note
            if label is not None:
                entry["label"] = label
            entry["updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self._data[key] = entry
            self._flush()
            return dict(entry)

    def delete(self, key: str) -> bool:
        with self._lock:
            existed = key in self._data
            self._data.pop(key, None)
            if existed:
                self._flush()
            return existed
