"""Guided hardware jobs built on pibench, driven by the File Cabinet's job engine.

The model does the digital part (probe, read, verify, back up); you do the physical
part (clip the chip, confirm pin 1). The first job is the Alienware BIOS dump, built
to mirror pibench's `aw15r2` profile and its runbook. Writing a cleared image back is
a separate, gated job — not part of the dump.
"""

from __future__ import annotations

import os
import re
import subprocess

from integrator.assistant import import_filecabinet


def _jobs():
    import_filecabinet()
    import filecabinet.jobs as jobs
    return jobs


# ---- runners -------------------------------------------------------------------
class SubprocessRunner:
    """Runs commands for real (on the Pi). Reads are safe; writes are gated by the engine."""

    def __init__(self, cwd: str | None = None, timeout: float = 600.0):
        self.cwd = cwd or os.getcwd()
        self.timeout = timeout

    def __call__(self, command: str):
        jobs = _jobs()
        try:
            p = subprocess.run(command, shell=True, cwd=self.cwd, capture_output=True,
                               text=True, timeout=self.timeout)
            return jobs.RunResult(p.returncode, p.stdout, p.stderr)
        except subprocess.TimeoutExpired:
            return jobs.RunResult(124, "", "timed out")
        except OSError as exc:
            return jobs.RunResult(127, "", str(exc))


class SimFlashrom:
    """A pretend flasher for testing and demos — no hardware, nothing written for real.

    chip_ok=False simulates the clip not seated (probe finds nothing); reads_match=False
    simulates a flaky in-circuit read (the two dumps differ). Flip them and re-run to
    exercise the engine's retry path."""

    def __init__(self, chip_ok: bool = True, reads_match: bool = True, writable=False):
        self.chip_ok, self.reads_match = chip_ok, reads_match
        self.writable = writable
        self.ran = []

    def __call__(self, command: str):
        jobs = _jobs()
        self.ran.append(command)
        low = command.lower()
        # probe: flashrom with no -r/-w
        if "flashrom" in low and " -r " not in low and " -w " not in low and "cmp" not in low:
            if self.chip_ok:
                return jobs.RunResult(0, "Found Winbond flash chip \"W25Q128.V\" (16384 kB, SPI).")
            return jobs.RunResult(1, "", "No EEPROM/flash device found.")
        if "cmp" in low or (" -r " in low and "&&" in low):  # read twice + compare
            return jobs.RunResult(0, "VERIFIED") if self.reads_match else jobs.RunResult(1, "", "files differ")
        if " -w " in low:  # write (gated)
            return jobs.RunResult(0, "Erase/write done. VERIFIED.") if self.writable else jobs.RunResult(1, "", "write-protected")
        return jobs.RunResult(0, "ok")  # cp, sha256sum, etc.


# ---- the Alienware BIOS-dump job ----------------------------------------------
def bios_dump_job(image: str = "aw15r2.bin", dev: str = "/dev/spidev0.0", spispeed: str = "256"):
    jobs = _jobs()
    fr = f"sudo flashrom -p linux_spi:dev={dev},spispeed={spispeed}"

    def probe_ok(res):
        found = bool(re.search(r"W25Q128|found .*flash chip", res.stdout, re.I))
        name = re.search(r'"([^"]+)"', res.stdout)
        return found, (f"found the chip ({name.group(1)})." if found and name else
                       "found the chip." if found else "no chip detected.")

    return jobs.Job(
        name="bios-dump",
        goal="a verified, backed-up BIOS dump of the Alienware",
        closing=(
            "You now have a verified dump, backed up as the untouched original. KEEP IT SAFE.\n"
            "I did NOT write anything to the chip. The next part — clearing the password inside the dump — "
            "is specific to this board, and we do it together with the dump in hand (a community tool for the "
            "LA-C912P, or a reputable .bin-cleaning service), then a separate, gated write-back job."
        ),
        steps=(
            jobs.Step(jobs.Kind.PHYSICAL,
                      "First, safety: make sure the laptop is fully off and the battery connector is "
                      "unplugged. Then clip the SOIC-8 clip onto the BIOS chip at silk UH4, matching pin 1 "
                      "(the little dot on the chip) to pin 1 on the clip. Don't power the Pi yet. Take a "
                      "photo of the clip seated so we can double-check pin 1. Say 'done' when it's clipped on."),
            jobs.Step(jobs.Kind.AUTO, "Probing the chip to confirm the clip and wiring:", f"{fr}",
                      check=probe_ok,
                      on_fail="I couldn't detect the chip. Reseat the clip, double-check pin 1, and if it "
                              "still won't read, lower the speed (I can retry at spispeed=128).",
                      retryable=True),
            jobs.Step(jobs.Kind.AUTO, "Reading the chip twice and checking the two dumps match:",
                      f"{fr} -r {image}.1 && {fr} -r {image}.2 && cmp {image}.1 {image}.2 && cp {image}.1 {image}",
                      on_fail="The two reads didn't match, so the dump isn't trustworthy yet. Reseat the clip "
                              "(in-circuit reads can be flaky) and I'll read again.",
                      retryable=True),
            jobs.Step(jobs.Kind.AUTO, "Saving an untouched backup and its checksum:",
                      f"cp {image} {image}.ORIGINAL.bin && sha256sum {image}.ORIGINAL.bin",
                      on_fail="I couldn't save the backup copy."),
        ),
    )


JOBS = {"bios-dump": bios_dump_job, "aw15r2": bios_dump_job}


def build(name: str, **kw):
    """Build a guided job by name, or return None if there isn't one."""
    builder = JOBS.get(name.lower())
    return builder(**kw) if builder else None
