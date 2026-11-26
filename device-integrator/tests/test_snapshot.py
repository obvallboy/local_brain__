import json

from integrator import snapshot


def test_build_snapshot_shape():
    snap = snapshot.build_snapshot()
    assert "source" in snap and snap["source"]
    for key in ("capabilities", "serial", "usb", "storage", "network"):
        assert key in snap


def test_main_prints_valid_json(capsys):
    snapshot.main([])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "source" in data
    assert isinstance(data["serial"], list)


def test_main_compact_is_single_line(capsys):
    snapshot.main(["--compact"])
    out = capsys.readouterr().out.strip()
    assert "\n" not in out
    json.loads(out)  # still valid JSON


def test_main_writes_output_file(tmp_path, capsys):
    path = tmp_path / "snap.json"
    snapshot.main(["-o", str(path)])
    assert path.exists()
    data = json.loads(path.read_text())
    assert "source" in data and "network" in data
