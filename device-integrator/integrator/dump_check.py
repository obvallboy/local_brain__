"""Is this chip dump real data? A second opinion on a read, before anyone trusts it.

Two reads that match (the BIOS job's `cmp`) prove the read was *stable*, not that it was
*right*: a clip that isn't touching gives two identical files of 0xFF. This looks inside
the dump and says what it is — blank, mirrored, a BIOS image, or unknown data — using
built-in checks that need nothing installed, plus binwalk's signature scan when it's on
the machine. It only ever reads the file; it never extracts or changes anything.
"""

from __future__ import annotations

import hashlib
import math
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from typing import Callable, List, Optional

# Byte patterns worth naming. (offset, bytes) pairs are checked at a fixed place;
# plain bytes are searched anywhere and counted.
INTEL_FLASH_DESCRIPTOR = (0x10, bytes.fromhex("5AA5F00F"))   # Intel IFD magic at 0x10
SIGNATURES = {
    b"_FVH": "UEFI firmware volume",
    b"$_IFLASH": "AMI Aptio flash tag",
    b"$IBIOSI$": "BIOS identification block",
    b"InsydeH2O": "Insyde H2O firmware",
    b"Phoenix": "Phoenix firmware string",
    b"$VSS": "UEFI variable store (where settings like passwords live)",
    b"$PDM": "Dell/Phoenix data module",
}
FLASH_SIZES = {2 ** n for n in range(15, 27)}   # 32 KB .. 64 MB


@dataclass
class DumpReport:
    path: str
    size: int
    sha256: str
    verdict: str                 # "bios" | "blank" | "mirrored" | "data" | "empty" | "unreadable"
    ok: bool                     # safe to treat as a real read?
    say: str                     # Devy's one-paragraph summary
    facts: List[str] = field(default_factory=list)
    binwalk: List[str] = field(default_factory=list)
    binwalk_available: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    n = len(data)
    return -sum(c / n * math.log2(c / n) for c in counts if c)


def _sample(data: bytes, limit: int = 1 << 20) -> bytes:
    """Entropy over a 16 MB image is slow in pure Python; 1 MB spread across it is plenty."""
    if len(data) <= limit:
        return data
    step = len(data) // 64
    chunk = limit // 64
    return b"".join(data[i:i + chunk] for i in range(0, len(data), step))[:limit]


def _fmt_size(n: float) -> str:
    if n < 1024:
        return f"{int(n)} bytes"
    for unit in ("KB", "MB", "GB"):
        n /= 1024
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if n == int(n) else f"{n:.1f} {unit}"
    return f"{n} GB"


BinwalkRunner = Callable[[str], Optional[List[str]]]


def run_binwalk(path: str, timeout: float = 120.0) -> Optional[List[str]]:
    """binwalk's signature scan as text lines, or None if binwalk isn't installed.
    Scan only — no -e, so nothing is extracted or written."""
    exe = shutil.which("binwalk")
    if not exe:
        return None
    try:
        p = subprocess.run([exe, path], capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return [f"(binwalk didn't finish: {exc})"]
    lines = [ln.rstrip() for ln in (p.stdout or "").splitlines() if ln.strip()]
    return [ln for ln in lines if not set(ln) <= set("-= ")][:60]


def check(path: str, binwalk: BinwalkRunner = run_binwalk, expected_size: Optional[int] = None) -> DumpReport:
    """Look inside a dump and say what it is. `expected_size` is the chip's size if known
    (16 MB for the Alienware's W25Q128)."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as exc:
        return DumpReport(path, 0, "", "unreadable", False, f"I couldn't open the dump: {exc}.")

    size = len(data)
    digest = hashlib.sha256(data).hexdigest()
    facts = [f"size: {_fmt_size(size)} ({size} bytes)", f"sha256: {digest}"]
    bw = binwalk(path) if size else None
    report = lambda verdict, ok, say: DumpReport(path, size, digest, verdict, ok, say, facts,
                                                 bw or [], bw is not None)

    if size == 0:
        return report("empty", False, "The dump is empty (0 bytes), so the read didn't produce anything.")

    if expected_size and size != expected_size:
        facts.append(f"expected {_fmt_size(expected_size)} for this chip")
    if size not in FLASH_SIZES:
        facts.append("not a standard flash-chip size, so it may be cut short")

    ff = data.count(0xFF) / size
    zero = data.count(0x00) / size
    facts.append(f"0xFF bytes: {ff:.1%} · 0x00 bytes: {zero:.1%}")

    if ff == 1.0:
        return report("blank", False,
                      "The dump is all 0xFF. That's what a read looks like when the clip isn't making contact "
                      "(or the chip is erased). Don't trust it: reseat the clip, check pin 1, and read again.")
    if zero == 1.0:
        return report("blank", False,
                      "The dump is all 0x00. That usually means the chip isn't powered or the data line is "
                      "stuck low. Don't trust it: check the clip, VCC and ground, then read again.")
    if len(set(data[:4096])) == 1 and len(set(_sample(data))) == 1:
        return report("blank", False,
                      f"The dump is the same byte (0x{data[0]:02X}) all the way through, which is not real data. "
                      "Reseat the clip and read again.")

    half = size // 2
    if size >= 2 * 1024 and size % 2 == 0 and data[:half] == data[half:]:
        return report("mirrored", False,
                      "The second half of the dump is an exact copy of the first. That happens when the chip's "
                      "size was detected wrong and the same data was read twice. Check that flashrom named the "
                      "right chip, then read again.")

    entropy = _entropy(_sample(data))
    facts.append(f"entropy: {entropy:.2f} bits/byte (8 = fully random or compressed)")

    found = []
    off, magic = INTEL_FLASH_DESCRIPTOR
    if data[off:off + len(magic)] == magic:
        found.append("Intel flash descriptor at 0x10")
    for sig, name in SIGNATURES.items():
        n = data.count(sig)
        if n:
            found.append(f"{name} ×{n}" if n > 1 else name)
    if found:
        facts.append("found: " + "; ".join(found))

    bios = any(s.startswith(("Intel flash descriptor", "UEFI firmware volume")) for s in found)
    if bios:
        return report("bios", True,
                      "This looks like a real BIOS/UEFI image: " + "; ".join(found[:4]) +
                      ". The read is believable. Keep this file untouched as the original and work only on copies.")
    if bw:
        return report("data", True,
                      "It's real-looking data, not blank, but I didn't find BIOS markers myself. binwalk's "
                      "findings are listed below. Fine for an EEPROM or a non-UEFI chip; for a laptop BIOS, "
                      "double-check the chip before going further.")
    return report("data", True,
                  "It's real-looking data, not blank or mirrored, but I didn't find BIOS markers. That's normal "
                  "for a small EEPROM. For a laptop BIOS chip it's worth a second look"
                  + ("." if bw is not None else " (installing binwalk gives a deeper scan)."))
