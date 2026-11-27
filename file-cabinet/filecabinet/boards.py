"""Recognize dev boards and USB-serial adapters from their USB id, offline.

Given a device's USB id (vid:pid), or failing that its product name, say what it is:
the board, the chip, the voltage, the usual baud rate, and how to program it. If it
isn't recognized, that's reported as unknown — never guessed.

The knowledge lives in data/usb_ids.json. Matches are ranked by how sure they are:
  exact   — the full vid:pid is known                  ("is a …")
  vendor  — only the vendor (vid) is known              ("is a … (a <vendor> device)")
  hint    — guessed from the product name               ("looks like a …")
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data" / "usb_ids.json"


@lru_cache(maxsize=1)
def _db() -> dict:
    return json.loads(DATA.read_text())


@dataclass(frozen=True)
class BoardInfo:
    name: str
    kind: str                 # board | bridge | bootloader | tool
    confidence: str           # exact | vendor | hint
    chip: str | None = None
    voltage: str | None = None
    baud: str | None = None
    tools: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    note: str | None = None

    @property
    def is_bridge(self) -> bool:
        return self.kind == "bridge"

    def summary_line(self) -> str:
        """The facts with no "is it plugged in" framing — for lists and general answers."""
        head = self.name
        spec = ", ".join(x for x in (self.chip, self.voltage) if x)
        if spec:
            head += f" ({spec})"
        if self.is_bridge:
            return head + " — a USB-to-serial bridge chip, not a board on its own"
        tail = ""
        if self.languages:
            tail = f" — program with {_join_or(self.languages)}"
            if self.tools:
                tail += f" using {_join_or(self.tools)}"
        if self.baud:
            tail += f"; serial {self.baud} baud"
        return head + tail

    def describe(self) -> str:
        """A short, honest sentence. Hedges when the match isn't exact."""
        lead = {"exact": "This is", "vendor": "This is", "hint": "This looks like"}[self.confidence]
        bits = [self.name]
        spec = ", ".join(x for x in (self.chip, self.voltage) if x)
        if spec:
            bits.append(f"({spec})")
        sentence = f"{lead} {_article(self.name)} {' '.join(bits)}."
        if self.is_bridge:
            sentence += (" That's a USB-to-serial chip, not a board on its own — the board behind it "
                         "could be an ESP32, an Arduino clone, or something else; I can't tell from the chip alone.")
        elif self.languages:
            sentence += f" Program it with {_join_or(self.languages)}"
            if self.tools:
                sentence += f" (using {_join_or(self.tools)})"
            sentence += "."
        if self.baud and not self.is_bridge:
            sentence += f" Serial runs at {self.baud} baud."
        if (note := self._note_tail()):
            sentence += f" {note}"
        return sentence

    def _note_tail(self) -> str | None:
        """The note, minus any part that just repeats the bridge sentence."""
        if not self.note:
            return None
        if self.is_bridge:
            trimmed = re.sub(r"^a usb-to-serial chip, not a board\.?\s*", "", self.note, flags=re.I)
            return trimmed[:1].upper() + trimmed[1:] if trimmed else None
        return self.note


def _make(entry: dict, confidence: str) -> BoardInfo:
    return BoardInfo(
        name=entry["name"],
        kind=entry.get("kind", "board"),
        confidence=confidence,
        chip=entry.get("chip"),
        voltage=entry.get("voltage"),
        baud=entry.get("baud"),
        tools=tuple(entry.get("tools", ())),
        languages=tuple(entry.get("languages", ())),
        note=entry.get("note"),
    )


def _norm(value) -> str:
    return re.sub(r"^0x", "", str(value or "").strip().lower())


def identify(vid=None, pid=None, product: str | None = None) -> BoardInfo | None:
    db = _db()
    v, p = _norm(vid), _norm(pid)
    if v and p and (entry := db["exact"].get(f"{v}:{p}")):
        return _make(entry, "exact")
    if v and (entry := db["vendor"].get(v)):
        return _make(entry, "vendor")
    if product:
        low = product.lower()
        for needle, entry in db["hints"]:
            if needle in low:
                return _make(entry, "hint")
    return None


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def _join_or(items) -> str:
    items = list(items)
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} or {items[1]}"
    return ", ".join(items[:-1]) + f", or {items[-1]}"
