"""SQLite storage for the drawers, the episode log and the core archive.

Everything lives in one local file. Nothing leaves the machine.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (           -- drawer 1: stable facts
    id INTEGER PRIMARY KEY,
    subject TEXT NOT NULL,
    fact TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS preferences (     -- drawer 1: quick opinions
    id INTEGER PRIMARY KEY,
    item TEXT NOT NULL UNIQUE,
    stance TEXT NOT NULL CHECK (stance IN ('like', 'dislike')),
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cases (           -- drawer 2: references
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    symptoms TEXT NOT NULL,
    signature TEXT NOT NULL,                 -- JSON: observed facts that identify the pattern
    fix TEXT NOT NULL,
    times_seen INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS episodes (        -- what happened, for recall by cue
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    place TEXT NOT NULL,
    activity TEXT NOT NULL,
    details TEXT NOT NULL,
    people TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS core_memories (   -- drawer 3: append-only
    id INTEGER PRIMARY KEY,
    memory TEXT NOT NULL,
    approved_by TEXT NOT NULL,
    approved_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS core_proposals (  -- waiting for owner approval
    id INTEGER PRIMARY KEY,
    memory TEXT NOT NULL,
    proposed_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected'))
);
CREATE TABLE IF NOT EXISTS corrections (     -- saved for the learning loop and new tests
    id INTEGER PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    correction TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS core_no_update BEFORE UPDATE ON core_memories
BEGIN SELECT RAISE(ABORT, 'core memories are append-only'); END;
CREATE TRIGGER IF NOT EXISTS core_no_delete BEFORE DELETE ON core_memories
BEGIN SELECT RAISE(ABORT, 'core memories are append-only'); END;
"""


@dataclass(frozen=True)
class Fact:
    id: int
    subject: str
    fact: str
    source: str


@dataclass(frozen=True)
class Case:
    id: int
    title: str
    symptoms: str
    signature: dict
    fix: str
    times_seen: int


@dataclass(frozen=True)
class Episode:
    id: int
    ts: datetime
    place: str
    activity: str
    details: str
    people: str

    def text(self) -> str:
        return f"{self.details} {self.place} {self.activity} {self.people}"


class Store:
    def __init__(self, path: str = ":memory:", now=datetime.now):
        # A web server answers from several threads; FileCabinet serializes access with a lock.
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        if path != ":memory:":
            self.db.execute("PRAGMA journal_mode=WAL")  # faster, crash-safe writes
        self.db.executescript(SCHEMA)
        self.now = now

    def _stamp(self) -> str:
        return self.now().isoformat(timespec="seconds")

    # ---- drawer 1 -------------------------------------------------------
    def add_fact(self, subject: str, fact: str, source: str = "owner") -> int:
        cur = self.db.execute(
            "INSERT INTO facts (subject, fact, source, created_at) VALUES (?, ?, ?, ?)",
            (subject.strip().lower(), fact.strip(), source, self._stamp()),
        )
        self.db.commit()
        return cur.lastrowid

    def facts(self) -> list[Fact]:
        rows = self.db.execute("SELECT id, subject, fact, source FROM facts ORDER BY id").fetchall()
        return [Fact(**dict(r)) for r in rows]

    def has_fact(self, subject: str) -> bool:
        row = self.db.execute("SELECT 1 FROM facts WHERE subject = ?", (subject.strip().lower(),)).fetchone()
        return row is not None

    def set_preference(self, item: str, stance: str, reason: str = "") -> None:
        self.db.execute(
            "INSERT INTO preferences (item, stance, reason, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(item) DO UPDATE SET stance = excluded.stance, reason = excluded.reason",
            (item.strip().lower(), stance, reason, self._stamp()),
        )
        self.db.commit()

    def preferences(self) -> dict[str, tuple[str, str]]:
        rows = self.db.execute("SELECT item, stance, reason FROM preferences").fetchall()
        return {r["item"]: (r["stance"], r["reason"]) for r in rows}

    # ---- drawer 2 -------------------------------------------------------
    def add_case(self, title: str, symptoms: str, signature: dict, fix: str) -> int:
        stamp = self._stamp()
        cur = self.db.execute(
            "INSERT INTO cases (title, symptoms, signature, fix, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (title, symptoms, json.dumps(signature, sort_keys=True), fix, stamp, stamp),
        )
        self.db.commit()
        return cur.lastrowid

    def reinforce_case(self, case_id: int) -> None:
        self.db.execute(
            "UPDATE cases SET times_seen = times_seen + 1, updated_at = ? WHERE id = ?",
            (self._stamp(), case_id),
        )
        self.db.commit()

    def cases(self) -> list[Case]:
        rows = self.db.execute(
            "SELECT id, title, symptoms, signature, fix, times_seen FROM cases ORDER BY id"
        ).fetchall()
        return [
            Case(r["id"], r["title"], r["symptoms"], json.loads(r["signature"]), r["fix"], r["times_seen"])
            for r in rows
        ]

    # ---- episode log ----------------------------------------------------
    def log_episode(self, place: str, activity: str, details: str, people: str = "", ts: datetime | None = None) -> int:
        stamp = (ts or self.now()).isoformat(timespec="seconds")
        cur = self.db.execute(
            "INSERT INTO episodes (ts, place, activity, details, people) VALUES (?, ?, ?, ?, ?)",
            (stamp, place.strip(), activity.strip(), details.strip(), people.strip()),
        )
        self.db.commit()
        return cur.lastrowid

    def episodes(self, start: datetime | None = None, end: datetime | None = None) -> list[Episode]:
        query, args = "SELECT * FROM episodes", []
        if start and end:
            query += " WHERE ts >= ? AND ts < ?"
            args = [start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")]
        rows = self.db.execute(query + " ORDER BY ts, id", args).fetchall()
        return [
            Episode(r["id"], datetime.fromisoformat(r["ts"]), r["place"], r["activity"], r["details"], r["people"])
            for r in rows
        ]

    def scene(self, anchor: Episode, minutes: int = 60) -> list[Episode]:
        """Everything logged at the same place around the same time as the anchor."""
        start, end = anchor.ts - timedelta(minutes=minutes), anchor.ts + timedelta(minutes=minutes)
        return [e for e in self.episodes(start, end) if e.place.lower() == anchor.place.lower()]

    # ---- drawer 3 archive ----------------------------------------------
    def propose_core(self, memory: str) -> int:
        cur = self.db.execute(
            "INSERT INTO core_proposals (memory, proposed_at) VALUES (?, ?)", (memory.strip(), self._stamp())
        )
        self.db.commit()
        return cur.lastrowid

    def pending_core(self) -> list[tuple[int, str]]:
        rows = self.db.execute(
            "SELECT id, memory FROM core_proposals WHERE status = 'pending' ORDER BY id"
        ).fetchall()
        return [(r["id"], r["memory"]) for r in rows]

    def approve_core(self, proposal_id: int, approved_by: str) -> int:
        row = self.db.execute(
            "SELECT memory FROM core_proposals WHERE id = ? AND status = 'pending'", (proposal_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"no pending core proposal #{proposal_id}")
        self.db.execute("UPDATE core_proposals SET status = 'approved' WHERE id = ?", (proposal_id,))
        cur = self.db.execute(
            "INSERT INTO core_memories (memory, approved_by, approved_at) VALUES (?, ?, ?)",
            (row["memory"], approved_by, self._stamp()),
        )
        self.db.commit()
        return cur.lastrowid

    def reject_core(self, proposal_id: int) -> None:
        self.db.execute(
            "UPDATE core_proposals SET status = 'rejected' WHERE id = ? AND status = 'pending'", (proposal_id,)
        )
        self.db.commit()

    def core_memories(self) -> list[tuple[int, str]]:
        rows = self.db.execute("SELECT id, memory FROM core_memories ORDER BY id").fetchall()
        return [(r["id"], r["memory"]) for r in rows]

    # ---- moving memory between machines -----------------------------------
    def export_data(self) -> dict:
        """Everything learned, as plain data (for copying between your laptop and desktop)."""
        rows = lambda q: [dict(r) for r in self.db.execute(q).fetchall()]  # noqa: E731
        return {
            "format": "file-cabinet/1",
            "facts": rows("SELECT subject, fact, source, created_at FROM facts ORDER BY id"),
            "preferences": rows("SELECT item, stance, reason, created_at FROM preferences ORDER BY id"),
            "cases": rows("SELECT title, symptoms, signature, fix, times_seen FROM cases ORDER BY id"),
            "episodes": rows("SELECT ts, place, activity, details, people FROM episodes ORDER BY ts, id"),
            "core_memories": rows("SELECT memory FROM core_memories ORDER BY id"),
        }

    def import_data(self, data: dict) -> dict:
        """Merge an export into this cabinet, skipping anything already here.

        Core memories are never written straight into drawer 3: they arrive as
        proposals and wait for the owner's /approve, like any other core change."""
        if data.get("format") != "file-cabinet/1":
            raise ValueError("not a File Cabinet export")
        added = {"facts": 0, "preferences": 0, "cases": 0, "episodes": 0, "core_proposals": 0}
        have = lambda q, args: self.db.execute(q, args).fetchone() is not None  # noqa: E731
        for f in data.get("facts", []):
            if not have("SELECT 1 FROM facts WHERE subject = ? AND fact = ?", (f["subject"], f["fact"])):
                self.db.execute("INSERT INTO facts (subject, fact, source, created_at) VALUES (?, ?, ?, ?)",
                                (f["subject"], f["fact"], f.get("source", "imported"), f.get("created_at", self._stamp())))
                added["facts"] += 1
        for pref in data.get("preferences", []):
            if not have("SELECT 1 FROM preferences WHERE item = ?", (pref["item"],)):
                self.db.execute("INSERT INTO preferences (item, stance, reason, created_at) VALUES (?, ?, ?, ?)",
                                (pref["item"], pref["stance"], pref.get("reason", ""), pref.get("created_at", self._stamp())))
                added["preferences"] += 1
        for c in data.get("cases", []):
            if not have("SELECT 1 FROM cases WHERE signature = ? AND fix = ?", (c["signature"], c["fix"])):
                stamp = self._stamp()
                self.db.execute("INSERT INTO cases (title, symptoms, signature, fix, times_seen, created_at, updated_at) "
                                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                                (c["title"], c["symptoms"], c["signature"], c["fix"], c.get("times_seen", 1), stamp, stamp))
                added["cases"] += 1
        for e in data.get("episodes", []):
            if not have("SELECT 1 FROM episodes WHERE ts = ? AND place = ? AND details = ?", (e["ts"], e["place"], e["details"])):
                self.db.execute("INSERT INTO episodes (ts, place, activity, details, people) VALUES (?, ?, ?, ?, ?)",
                                (e["ts"], e["place"], e["activity"], e["details"], e.get("people", "")))
                added["episodes"] += 1
        known = {m for _, m in self.core_memories()} | {m for _, m in self.pending_core()}
        for c in data.get("core_memories", []):
            if c["memory"] not in known:
                self.db.execute("INSERT INTO core_proposals (memory, proposed_at) VALUES (?, ?)", (c["memory"], self._stamp()))
                added["core_proposals"] += 1
        self.db.commit()
        return added

    # ---- corrections ----------------------------------------------------
    def add_correction(self, question: str, answer: str, correction: str) -> int:
        cur = self.db.execute(
            "INSERT INTO corrections (question, answer, correction, created_at) VALUES (?, ?, ?, ?)",
            (question, answer, correction, self._stamp()),
        )
        self.db.commit()
        return cur.lastrowid
