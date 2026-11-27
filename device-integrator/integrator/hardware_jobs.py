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


# ---- I2C EEPROM read (mirrors the pibench i2c-eeprom profile) ------------------
class SimI2C:
    """A pretend I2C bus for testing: i2cdetect shows the chip (or not), reads succeed."""

    def __init__(self, addr_present: bool = True, addr: str = "50"):
        self.addr_present, self.addr = addr_present, addr
        self.ran = []

    def __call__(self, command: str):
        jobs = _jobs()
        self.ran.append(command)
        if "i2cdetect" in command:
            grid = "     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f\n50: " + \
                   (self.addr if self.addr_present else "--")
            return jobs.RunResult(0, grid)
        return jobs.RunResult(0, "ok")  # dd/i2cdump read, cp, sha256sum


def eeprom_read_job(bus: str = "1", addr: str = "0x50", out: str = "eeprom.bin"):
    jobs = _jobs()
    addr_hex = addr.lower().replace("0x", "")

    def saw_chip(res):
        # i2cdetect rows start with a label like "50:"; the chip shows as a cell "50" (vs "--").
        # Strip the row labels first so the label isn't mistaken for a detected address.
        cells = re.sub(r"(?mi)^\s*[0-9a-f]{2}:", "", res.stdout).lower().split()
        found = addr_hex in cells
        return found, f"found a chip at {addr}." if found else f"nothing at {addr} on the bus."

    sysfs = f"/sys/bus/i2c/devices/{bus}-00{addr_hex}/eeprom"
    return jobs.Job(
        name="eeprom-read",
        goal="a verified, backed-up dump of the I2C EEPROM",
        closing=(
            "You have a dump, backed up as the untouched original — KEEP IT SAFE. On some laptops the "
            "system/BIOS password or service data lives in this little chip. I did NOT change anything. "
            "If we need to edit it, we do that on a copy, with the WP pin set to writable, as a separate step."
        ),
        steps=(
            jobs.Step(jobs.Kind.PHYSICAL,
                      "Power the board off. Wire the 24Cxx EEPROM to the Pi's I2C: SDA->pin 3, SCL->pin 5, "
                      "GND->pin 6, VCC->3V3 (pin 1). Tie A0/A1/A2 per your board (all to GND is address 0x50), "
                      "and WP (pin 7) to GND so it's readable. 3.3 V only. Say 'done' when it's wired."),
            jobs.Step(jobs.Kind.AUTO, "Scanning the I2C bus for the chip:", f"sudo i2cdetect -y {bus}",
                      check=saw_chip,
                      on_fail="I don't see the chip on the bus. Check SDA/SCL aren't swapped, the ground and "
                              "power, and the address jumpers (A0-A2).",
                      retryable=True),
            jobs.Step(jobs.Kind.AUTO, "Reading the EEPROM and saving an untouched backup:",
                      f"(sudo dd if={sysfs} of={out} 2>/dev/null || sudo i2cdump -y -r 0-255 {bus} {addr} > {out}) "
                      f"&& cp {out} {out}.ORIGINAL.bin && sha256sum {out}.ORIGINAL.bin",
                      on_fail="I couldn't read the EEPROM. The kernel eeprom driver may not be bound; we can try "
                              "i2cdump instead."),
        ),
    )


# ---- Serial-console session (uses the serial scanner, not just shell) -----------
def serial_console_job(port: str = "/dev/serial0", reader=None):
    jobs = _jobs()

    def scan():
        import_filecabinet()
        from filecabinet.serialscan import detect_baud, recognize, report
        r = reader
        if r is None:
            from integrator.serial_help import make_reader
            try:
                r = make_reader(port)
            except ImportError:
                return jobs.RunResult(1, "", "pyserial not installed")
        result = detect_baud(r)
        reading = recognize(result.sample) if result else None
        return jobs.RunResult(0 if result else 1, report(result, reading))

    return jobs.Job(
        name="serial-console",
        goal="find the board's serial settings and see what it's running",
        closing=(f"Once you know the baud rate, open a live console with  tio -b <baud> {port}  "
                 "(or picocom). Ctrl-] quits tio."),
        steps=(
            jobs.Step(jobs.Kind.PHYSICAL,
                      "3.3 V ONLY — never wire a 5 V or RS-232 line to the Pi. Connect the board's TX to the "
                      "Pi's RX (pin 10), the board's RX to the Pi's TX (pin 8), and share GND (pin 6). Do NOT "
                      "connect the board's Vcc. Power the board from its own supply. Say 'done' when it's wired."),
            jobs.Step(jobs.Kind.AUTO, "Listening and trying the common baud rates:", call=scan,
                      name="serial baud scan + recognize",
                      on_fail="I couldn't get readable text at any common baud. Check that TX/RX aren't swapped, "
                              "that GND is shared, and that the board is powered and actually sending.",
                      retryable=True),
        ),
    )


JOBS = {
    "bios-dump": bios_dump_job, "aw15r2": bios_dump_job,
    "eeprom-read": eeprom_read_job, "i2c-eeprom": eeprom_read_job,
    "serial-console": serial_console_job, "uart": serial_console_job,
}


def build(name: str, **kw):
    """Build a guided job by name, or return None if there isn't one."""
    builder = JOBS.get(name.lower())
    return builder(**kw) if builder else None
