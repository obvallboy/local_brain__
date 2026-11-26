"""Drawer 3: core values and core memories.

Values are loaded once into frozen objects and fingerprinted, so nothing at
runtime can change them. Core memories are append-only in the database, and a
new one only enters after the owner approves it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .similarity import similarity
from .store import Store

DEFAULT_VALUES = Path(__file__).parent / "data" / "values.json"


@dataclass(frozen=True)
class Value:
    id: str
    text: str


class Core:
    def __init__(self, store: Store, values_path: Path | str = DEFAULT_VALUES):
        self._path = Path(values_path)
        raw = self._path.read_bytes()
        self._fingerprint = hashlib.sha256(raw).hexdigest()
        data = json.loads(raw)
        self.identity: str = data["identity"]
        self.values: tuple[Value, ...] = tuple(Value(v["id"], v["text"]) for v in data["values"])
        self._store = store

    def intact(self) -> bool:
        """True if the values file on disk still matches what was loaded."""
        return hashlib.sha256(self._path.read_bytes()).hexdigest() == self._fingerprint

    def guide(self) -> str:
        lines = [self.identity, "Core values:"]
        lines += [f"- {v.text}" for v in self.values]
        return "\n".join(lines)

    def memories(self) -> list[tuple[int, str]]:
        return self._store.core_memories()

    def find_memory(self, text: str, threshold: float = 0.3) -> tuple[int, str] | None:
        scored = [(similarity(text, m), mid, m) for mid, m in self.memories()]
        scored = [s for s in scored if s[0] >= threshold]
        if not scored:
            return None
        _, mid, memory = max(scored)
        return mid, memory

    def approve(self, proposal_id: int, approved_by: str) -> int:
        """Only the owner moves a proposal into drawer 3."""
        if not approved_by.strip():
            raise PermissionError("a core memory needs the owner's approval")
        return self._store.approve_core(proposal_id, approved_by)
