"""The guided-job engine: the model runs the digital steps, you do the physical ones."""

from filecabinet.jobs import Job, Kind, RunResult, Session, Step


class FakeRunner:
    """Records commands and returns canned results keyed by a substring."""

    def __init__(self, results=None, default=RunResult(0, "ok")):
        self.results = results or {}
        self.default = default
        self.ran = []

    def __call__(self, command):
        self.ran.append(command)
        for key, res in self.results.items():
            if key in command:
                return res
        return self.default


def _found_chip(res: RunResult):
    found = "W25Q128" in res.stdout
    return found, "found the chip." if found else "no chip detected."


def sample_job():
    return Job("demo", "flash the board", (
        Step(Kind.PHYSICAL, "Plug the board in and hold the button."),
        Step(Kind.AUTO, "Checking the chip:", "probe", check=_found_chip,
             on_fail="I couldn't detect the chip.", retryable=True),
        Step(Kind.AUTO, "Reading it twice and comparing:", "read-verify",
             on_fail="The two reads differ.", retryable=True),
        Step(Kind.GATED, "I'll write the new image to the chip.", "write",
             on_fail="The write failed."),
    ))


def test_physical_step_waits_for_done():
    r = FakeRunner({"probe": RunResult(0, "Found W25Q128")})
    s = Session(sample_job(), r)
    first = s.start()
    assert first.awaiting == "physical"
    assert "Plug the board in" in first.say
    assert r.ran == []  # nothing digital ran before the physical step


def test_runs_safe_steps_itself_then_gates_the_write():
    r = FakeRunner({"probe": RunResult(0, "Found W25Q128")})
    s = Session(sample_job(), r)
    s.start()
    turn = s.user("done")
    # It ran probe and read-verify on its own, then stopped to ask before writing.
    assert "probe" in r.ran and "read-verify" in r.ran and "write" not in r.ran
    assert turn.awaiting == "confirm"
    assert "found the chip" in turn.say and "can't be undone" in turn.say


def test_go_runs_the_gated_step():
    r = FakeRunner({"probe": RunResult(0, "Found W25Q128")})
    s = Session(sample_job(), r)
    s.start(); s.user("done")
    turn = s.user("go")
    assert "write" in r.ran and turn.done


def test_no_stops_before_the_irreversible_step():
    r = FakeRunner({"probe": RunResult(0, "Found W25Q128")})
    s = Session(sample_job(), r)
    s.start(); s.user("done")
    turn = s.user("no")
    assert "write" not in r.ran and turn.done and "nothing was written" in turn.say


def test_a_failing_check_offers_a_retry():
    r = FakeRunner({"probe": RunResult(0, "nothing here")})  # no W25Q128 -> probe check fails
    s = Session(sample_job(), r)
    s.start()
    turn = s.user("done")
    assert turn.awaiting == "retry"
    assert "couldn't detect the chip" in turn.say


def test_retry_reruns_the_same_step_then_continues():
    r = FakeRunner({"probe": RunResult(0, "nothing here")})
    s = Session(sample_job(), r)
    s.start(); s.user("done")
    r.results["probe"] = RunResult(0, "Found W25Q128")  # the user reseated the clip
    turn = s.user("retry")
    assert r.ran.count("probe") == 2
    assert turn.awaiting == "confirm"  # moved on to the gated write


def test_stop_halts_everything():
    r = FakeRunner()
    s = Session(sample_job(), r)
    s.start()
    turn = s.user("stop")
    assert turn.done and r.ran == []


def test_narration_shows_what_it_did():
    r = FakeRunner({"probe": RunResult(0, "Found W25Q128")})
    s = Session(sample_job(), r)
    s.start()
    turn = s.user("done")
    assert "Checking the chip:" in turn.say and "Reading it twice" in turn.say
    assert turn.ran == ("probe", "read-verify")
