"""The Alienware BIOS-dump guided job, driven end to end with a simulated flasher."""

from integrator.assistant import import_filecabinet
from integrator.hardware_jobs import SimFlashrom, bios_dump_job


def session(sim):
    import_filecabinet()
    from filecabinet.jobs import Session
    return Session(bios_dump_job(), sim)


def test_happy_path_does_the_digital_work_and_never_writes():
    sim = SimFlashrom()
    s = session(sim)

    first = s.start()
    assert first.awaiting == "physical"                 # it waits for you to clip the chip
    assert "pin 1" in first.say and sim.ran == []

    done = s.user("done")                               # you clipped it on
    # It probed, read twice, verified, and backed up — all by itself.
    assert any("flashrom" in c and "-r" not in c for c in sim.ran)        # probe
    assert any("cmp" in c for c in sim.ran)                                # read + verify
    assert any("ORIGINAL.bin" in c for c in sim.ran)                       # backup
    assert not any(" -w " in c for c in sim.ran)                           # never wrote
    assert done.done
    assert "found the chip (W25Q128.V)" in done.say
    assert "KEEP IT SAFE" in done.say and "did NOT write" in done.say


def test_clip_not_seated_offers_a_retry_then_recovers():
    sim = SimFlashrom(chip_ok=False)
    s = session(sim)
    s.start()
    turn = s.user("done")
    assert turn.awaiting == "retry"
    assert "couldn't detect the chip" in turn.say

    sim.chip_ok = True                                  # you reseat the clip
    turn = s.user("retry")
    assert sim.ran.count  # ran probe again
    assert turn.done and "KEEP IT SAFE" in turn.say


def test_flaky_reads_are_caught_not_trusted():
    sim = SimFlashrom(reads_match=False)
    s = session(sim)
    s.start()
    turn = s.user("done")
    assert turn.awaiting == "retry"
    assert "didn't match" in turn.say
    # It did not save a backup from an untrustworthy read.
    assert not any("ORIGINAL.bin" in c for c in sim.ran)


def test_you_can_stop_at_the_physical_step():
    sim = SimFlashrom()
    s = session(sim)
    s.start()
    turn = s.user("stop")
    assert turn.done and sim.ran == []
