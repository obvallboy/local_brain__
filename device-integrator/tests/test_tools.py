"""The chip-dump checker and the approval-gated MicroPython runner, with no hardware."""

import io
import os
import subprocess

import pytest

from app import create_app
from integrator import dump_check, micropython
from integrator.assistant import import_filecabinet
from integrator.hardware_jobs import SimFlashrom, bios_dump_job

MB = 1024 * 1024
no_binwalk = lambda path: None


def write(tmp_path, data, name="dump.bin"):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


# ---- dump check ----------------------------------------------------------------
def test_all_ff_is_a_failed_read(tmp_path):
    rep = dump_check.check(write(tmp_path, b"\xff" * MB), binwalk=no_binwalk)
    assert rep.verdict == "blank" and not rep.ok
    assert "clip" in rep.say


def test_all_zero_is_a_failed_read(tmp_path):
    rep = dump_check.check(write(tmp_path, b"\x00" * MB), binwalk=no_binwalk)
    assert rep.verdict == "blank" and not rep.ok


def test_mirrored_halves_are_caught(tmp_path):
    half = os.urandom(MB // 2)
    rep = dump_check.check(write(tmp_path, half + half), binwalk=no_binwalk)
    assert rep.verdict == "mirrored" and not rep.ok


def test_bios_image_is_recognized(tmp_path):
    data = bytearray(os.urandom(2 * MB))
    data[0x10:0x14] = bytes.fromhex("5AA5F00F")          # Intel flash descriptor
    data[0x1000:0x1004] = b"_FVH"                         # a UEFI firmware volume
    data[0x9000:0x9004] = b"$VSS"                         # a variable store
    rep = dump_check.check(write(tmp_path, bytes(data)), binwalk=no_binwalk, expected_size=2 * MB)
    assert rep.verdict == "bios" and rep.ok
    assert "Intel flash descriptor" in rep.say
    assert any("variable store" in f for f in rep.facts)
    assert rep.sha256 and len(rep.sha256) == 64


def test_plain_data_is_ok_but_not_called_a_bios(tmp_path):
    rep = dump_check.check(write(tmp_path, os.urandom(256)), binwalk=no_binwalk)
    assert rep.verdict == "data" and rep.ok
    assert "installing binwalk" in rep.say
    assert any("not a standard flash-chip size" in f for f in rep.facts)


def test_empty_and_missing_files(tmp_path):
    assert dump_check.check(write(tmp_path, b""), binwalk=no_binwalk).verdict == "empty"
    assert dump_check.check(str(tmp_path / "nope.bin"), binwalk=no_binwalk).verdict == "unreadable"


def test_binwalk_findings_are_included_when_available(tmp_path):
    lines = ["DECIMAL  HEXADECIMAL  DESCRIPTION", "0  0x0  UEFI PI firmware volume"]
    rep = dump_check.check(write(tmp_path, os.urandom(4096)), binwalk=lambda p: lines)
    assert rep.binwalk_available and rep.binwalk == lines


# ---- the BIOS job uses it, and a bad dump means a fresh read --------------------
def test_blank_dump_in_the_job_rereads_then_rechecks():
    import_filecabinet()
    from filecabinet.jobs import RunResult, Session

    results = iter([RunResult(1, "", "The dump is all 0xFF."), RunResult(0, "This looks like a real BIOS/UEFI image.")])
    sim = SimFlashrom()
    s = Session(bios_dump_job(checker=lambda image: next(results)), sim)
    s.start()
    turn = s.user("done")
    assert turn.awaiting == "retry" and "0xFF" in turn.say
    reads_before = sum("cmp" in c for c in sim.ran)

    done = s.user("retry")
    assert sum("cmp" in c for c in sim.ran) == reads_before + 1      # it read the chip again
    assert done.done and "real BIOS" in done.say
    assert not any(" -w " in c for c in sim.ran)


# ---- MicroPython runner ----------------------------------------------------------
def test_ports_are_validated():
    with pytest.raises(ValueError):
        micropython.validate("/dev/ttyS0", "print(1)")               # empty built-in port
    with pytest.raises(ValueError):
        micropython.validate("/etc/passwd", "print(1)")
    with pytest.raises(ValueError):
        micropython.validate("/dev/ttyACM0", "   ")
    micropython.validate("/dev/ttyACM0", "print(1)")
    micropython.validate("/dev/serial/by-id/usb-MicroPython_Board_e66-if00", "print(1)")


def test_a_plan_runs_once_and_expires():
    now = [0.0]
    planner = micropython.Planner(ttl=60, clock=lambda: now[0])
    plan = planner.plan("/dev/ttyACM0", "print('hi')")
    assert plan["command"] == "mpremote connect /dev/ttyACM0 run devy_snippet.py"
    assert planner.take(plan["token"]) == ("/dev/ttyACM0", "print('hi')")
    with pytest.raises(KeyError):
        planner.take(plan["token"])                                    # used up

    late = planner.plan("/dev/ttyACM0", "print('hi')")
    now[0] = 61
    with pytest.raises(KeyError):
        planner.take(late["token"])                                    # expired


def fake_exec(stdout="", stderr="", rc=0, timeout=False, seen=None):
    def run(argv, **kw):
        if seen is not None:
            seen.append((argv, open(argv[-1]).read()))
        if timeout:
            raise subprocess.TimeoutExpired(argv, kw.get("timeout"), output=b"partial", stderr=b"")
        return subprocess.CompletedProcess(argv, rc, stdout, stderr)
    return run


@pytest.fixture
def mpremote(monkeypatch):
    monkeypatch.setattr(micropython, "mpremote_path", lambda: "/usr/bin/mpremote")


def test_run_reports_what_the_board_printed(mpremote):
    seen = []
    r = micropython.run("/dev/ttyACM0", "print('hello')", exec_=fake_exec("hello\n", seen=seen))
    assert r["ok"] and r["label"] == "I ran it" and r["stdout"] == "hello\n"
    argv, code = seen[0]
    assert argv[:4] == ["/usr/bin/mpremote", "connect", "/dev/ttyACM0", "run"] and code == "print('hello')"
    assert not os.path.exists(argv[-1])                               # temp file cleaned up


def test_a_traceback_is_a_failed_run(mpremote):
    tb = "Traceback (most recent call last):\n  File \"<stdin>\", line 1\nNameError: name 'x' isn't defined\n"
    r = micropython.run("/dev/ttyACM0", "x", exec_=fake_exec(tb, rc=1))
    assert not r["ok"] and r["label"] == "I ran it" and "error" in r["say"]


def test_a_hang_is_stopped_and_explained(mpremote):
    r = micropython.run("/dev/ttyACM0", "while True: pass", timeout=1, exec_=fake_exec(timeout=True))
    assert not r["ok"] and r["timed_out"] and "replug" in r["say"]


def test_list_boards_skips_empty_ports(monkeypatch, mpremote):
    out = ("/dev/ttyS0 None 0000:0000 None None\n"
           "/dev/ttyACM0 e6614c311b7e6f35 2e8a:0005 MicroPython Board in FS mode\n")
    boards = micropython.list_boards(exec_=fake_exec(out))
    assert [b["port"] for b in boards] == ["/dev/ttyACM0"]
    assert boards[0]["vid"] == "2e8a" and boards[0]["product"] == "Board in FS mode"


# ---- API --------------------------------------------------------------------------
@pytest.fixture
def client(tmp_path):
    app = create_app(data_dir=str(tmp_path))
    app.config["TESTING"] = True
    return app.test_client()


def test_api_runs_only_a_reviewed_plan(client, monkeypatch):
    ran = []
    monkeypatch.setattr(micropython, "run", lambda port, code: ran.append((port, code)) or {"ok": True})
    assert client.post("/api/tools/micropython/run", json={"token": "made-up"}).status_code == 409
    assert ran == []

    plan = client.post("/api/tools/micropython/plan", json={"port": "/dev/ttyACM0", "code": "print(1)"}).get_json()
    assert client.post("/api/tools/micropython/run", json={"token": plan["token"]}).get_json() == {"ok": True}
    assert ran == [("/dev/ttyACM0", "print(1)")]
    assert client.post("/api/tools/micropython/run", json={"token": plan["token"]}).status_code == 409


def test_api_rejects_a_plan_for_a_placeholder_port(client):
    r = client.post("/api/tools/micropython/plan", json={"port": "/dev/ttyS4", "code": "print(1)"})
    assert r.status_code == 400


def test_api_checks_an_uploaded_dump(client):
    r = client.post("/api/tools/dump-check", data={"file": (io.BytesIO(b"\xff" * 65536), "aw15r2.bin")},
                    content_type="multipart/form-data")
    body = r.get_json()
    assert r.status_code == 200 and body["verdict"] == "blank" and body["path"] == "aw15r2.bin"


def test_api_tools_status(client):
    body = client.get("/api/tools").get_json()
    assert set(body) == {"binwalk", "mpremote"}


def test_a_missing_board_gets_a_plain_answer(mpremote):
    err = "mpremote: failed to access /dev/ttyACM9 (it may be in use by another program)\n"
    r = micropython.run("/dev/ttyACM9", "print(1)", exec_=fake_exec(stderr=err, rc=1))
    assert not r["ok"] and r["label"] == "I'm not sure" and "plugged in" in r["say"]


def test_permission_denied_points_at_the_uucp_group(mpremote):
    err = "mpremote: could not open port /dev/ttyACM0: [Errno 13] Permission denied\n"
    r = micropython.run("/dev/ttyACM0", "print(1)", exec_=fake_exec(stderr=err, rc=1))
    assert "uucp" in r["say"]
