import json

from integrator.notes import NotesStore


def test_set_get_roundtrip(tmp_path):
    store = NotesStore(str(tmp_path / "notes.json"))
    store.set("usb:10c4:ea60", note="UART bridge", label="CP2102")
    entry = store.get("usb:10c4:ea60")
    assert entry["note"] == "UART bridge"
    assert entry["label"] == "CP2102"
    assert "updated" in entry


def test_partial_update_keeps_other_field(tmp_path):
    store = NotesStore(str(tmp_path / "notes.json"))
    store.set("k", note="n1", label="L")
    store.set("k", note="n2")  # label omitted
    entry = store.get("k")
    assert entry["note"] == "n2"
    assert entry["label"] == "L"


def test_persists_across_instances(tmp_path):
    path = str(tmp_path / "notes.json")
    NotesStore(path).set("serial:/dev/ttyUSB0", note="9600 8N1")
    reopened = NotesStore(path)
    assert reopened.get("serial:/dev/ttyUSB0")["note"] == "9600 8N1"


def test_delete(tmp_path):
    store = NotesStore(str(tmp_path / "notes.json"))
    store.set("k", note="x")
    assert store.delete("k") is True
    assert store.get("k") == {}
    assert store.delete("k") is False


def test_corrupt_file_is_recovered(tmp_path):
    path = tmp_path / "notes.json"
    path.write_text("{ this is not json")
    store = NotesStore(str(path))          # must not raise
    assert store.all() == {}
    assert (tmp_path / "notes.json.corrupt").exists()
    store.set("k", note="fresh")
    assert json.loads(path.read_text())["k"]["note"] == "fresh"


def test_empty_key_rejected(tmp_path):
    store = NotesStore(str(tmp_path / "notes.json"))
    try:
        store.set("", note="x")
        assert False, "expected ValueError"
    except ValueError:
        pass
