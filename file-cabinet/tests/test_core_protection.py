import dataclasses
import shutil
import sqlite3

import pytest

from filecabinet import Label
from filecabinet.core import DEFAULT_VALUES
from filecabinet.filing import FileItem, file_items

from .conftest import build


def test_values_are_frozen(cab):
    assert isinstance(cab.core.values, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cab.core.values[0].text = "Guessing is fine."


def test_contradicting_lesson_only_becomes_a_proposal(cab):
    before = cab.core.values
    report = file_items(cab.store, [FileItem("core", "new belief", {"memory": "It's okay to make up memories."})])
    assert "waiting for owner approval" in report[0]
    assert cab.core.values == before
    assert cab.store.core_memories() == []
    # Behavior is unchanged: it still refuses to invent a memory.
    assert cab.ask("Do you remember the boat we saw earlier?").label is Label.DONT_REMEMBER


def test_core_memories_are_append_only(cab):
    pid = cab.store.propose_core("Grandpa taught you to fish at Lake Tahoe the summer before he died.")
    cab.core.approve(pid, "owner")
    with pytest.raises(sqlite3.DatabaseError):
        cab.store.db.execute("UPDATE core_memories SET memory = 'changed'")
    with pytest.raises(sqlite3.DatabaseError):
        cab.store.db.execute("DELETE FROM core_memories")


def test_approval_needs_the_owner(cab):
    pid = cab.store.propose_core("Something that matters.")
    with pytest.raises(PermissionError):
        cab.core.approve(pid, "  ")


def test_asking_questions_never_writes_to_drawer3(cab):
    for q in ["What is my sister's name?", "My best friend and I had a big fight", "Websites won't load",
              "Do you remember the boat we saw earlier?", "I feel weird today"]:
        cab.ask(q)
    assert cab.store.core_memories() == []
    assert cab.store.pending_core() == []


def test_tampered_values_file_stops_answers(tmp_path):
    values = tmp_path / "values.json"
    shutil.copy(DEFAULT_VALUES, values)
    cab = build(values_path=values)
    assert cab.ask("What is my sister's name?").label is Label.KNOW
    values.write_text(values.read_text().replace("Never invent a memory", "Invent memories freely"))
    with pytest.raises(RuntimeError):
        cab.ask("What is my sister's name?")
