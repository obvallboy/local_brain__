"""The Alienware BIOS-dump guided job, driven end to end with a simulated flasher."""

from integrator.assistant import import_filecabinet
from integrator.hardware_jobs import SimFlashrom, bios_dump_job


def real_dump(image):
    """The simulated flasher writes no file, so stand in for a dump check that passes."""
    from filecabinet.jobs import RunResult
    return RunResult(0, "This looks like a real BIOS/UEFI image.")


def session(sim, checker=real_dump):
    import_filecabinet()
    from filecabinet.jobs import Session
    return Session(bios_dump_job(checker=checker), sim)


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


# ---- I2C EEPROM read ----------------------------------------------------------------
def eeprom_session(sim):
    import_filecabinet()
    from filecabinet.jobs import Session
    from integrator.hardware_jobs import eeprom_read_job
    return Session(eeprom_read_job(), sim)


def test_eeprom_read_happy_path():
    from integrator.hardware_jobs import SimI2C
    sim = SimI2C()
    s = eeprom_session(sim)
    assert s.start().awaiting == "physical" and sim.ran == []
    done = s.user("done")
    assert any("i2cdetect" in c for c in sim.ran)
    assert any("ORIGINAL.bin" in c for c in sim.ran)
    assert done.done and "found a chip at 0x50" in done.say and "KEEP IT SAFE" in done.say


def test_eeprom_chip_not_on_bus_retries():
    from integrator.hardware_jobs import SimI2C
    sim = SimI2C(addr_present=False)
    s = eeprom_session(sim)
    s.start()
    turn = s.user("done")
    assert turn.awaiting == "retry" and "don't see the chip" in turn.say
    assert not any("ORIGINAL.bin" in c for c in sim.ran)  # no backup from a missing chip


# ---- Serial console session ---------------------------------------------------------
def test_serial_console_recognizes_the_board():
    import_filecabinet()
    from filecabinet.jobs import Session
    from integrator.hardware_jobs import serial_console_job
    # A fake reader: readable MicroPython text at 115200, noise elsewhere.
    def reader(baud):
        return b"MicroPython v1.24\r\n>>> " if baud == 115200 else bytes([0xFF, 0x00, 0x80])
    s = Session(serial_console_job(reader=reader), lambda cmd: None)
    assert s.start().awaiting == "physical"
    turn = s.user("done")
    assert turn.done
    assert "115200 baud" in turn.say and "MicroPython" in turn.say
    assert "tio -b" in turn.say  # the closing tells you how to open a live console


def test_serial_console_nothing_readable_retries():
    import_filecabinet()
    from filecabinet.jobs import Session
    from integrator.hardware_jobs import serial_console_job
    s = Session(serial_console_job(reader=lambda b: bytes([0xFF, 0x00, 0xC1])), lambda cmd: None)
    s.start()
    turn = s.user("done")
    assert turn.awaiting == "retry" and "couldn't get readable text" in turn.say
