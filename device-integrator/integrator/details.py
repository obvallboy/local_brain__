"""Deep inspection helpers for a single device.

Reads sysfs attribute trees (Linux) and filters kernel ring-buffer lines so
you can see what the kernel said about a device when it was plugged in. All
read-only; dmesg access that requires privileges is caught and reported
rather than raised.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any, Dict, List, Optional


# Small sysfs files worth surfacing for a USB device node.
_USB_ATTRS = [
    "idVendor",
    "idProduct",
    "manufacturer",
    "product",
    "serial",
    "busnum",
    "devnum",
    "version",
    "speed",
    "bDeviceClass",
    "bDeviceSubClass",
    "bDeviceProtocol",
    "bNumConfigurations",
    "bNumInterfaces",
    "bmAttributes",
    "bMaxPower",
    "maxchild",
    "quirks",
    "removable",
]


def sysfs_attrs(path: str, names: Optional[List[str]] = None) -> Dict[str, str]:
    """Read a set of small attribute files from a sysfs directory."""
    result: Dict[str, str] = {}
    if not path or not os.path.isdir(path):
        return result
    names = names or _USB_ATTRS
    for name in names:
        fpath = os.path.join(path, name)
        try:
            if os.path.isfile(fpath):
                with open(fpath, "r", errors="replace") as fh:
                    value = fh.read().strip()
                if value != "":
                    result[name] = value
        except Exception:
            continue
    return result


def usb_interfaces(path: str) -> List[Dict[str, Any]]:
    """Enumerate the interfaces of a USB device from its sysfs directory."""
    interfaces: List[Dict[str, Any]] = []
    if not path or not os.path.isdir(path):
        return interfaces
    base = os.path.basename(path.rstrip("/"))
    try:
        entries = sorted(os.listdir(path))
    except Exception:
        return interfaces
    for entry in entries:
        # Interface dirs look like "1-1:1.0" under the device dir "1-1".
        if not entry.startswith(base + ":"):
            continue
        ipath = os.path.join(path, entry)
        attrs = sysfs_attrs(
            ipath,
            [
                "bInterfaceNumber",
                "bInterfaceClass",
                "bInterfaceSubClass",
                "bInterfaceProtocol",
                "bNumEndpoints",
            ],
        )
        driver = None
        drv_link = os.path.join(ipath, "driver")
        if os.path.islink(drv_link):
            driver = os.path.basename(os.path.realpath(drv_link))
        attrs["interface"] = entry
        attrs["driver"] = driver
        interfaces.append(attrs)
    return interfaces


def dmesg_lines(tokens: List[str], limit: int = 60) -> Dict[str, Any]:
    """Return recent kernel log lines matching any of ``tokens``.

    ``tokens`` are case-insensitive substrings — e.g. a tty name
    (``ttyUSB0``), a vid:pid (``10c4:ea60``) or a driver name. If dmesg is
    unavailable or needs privileges, that is reported in ``error``.
    """
    if shutil.which("dmesg") is None:
        return {"available": False, "error": "dmesg not found on PATH", "lines": []}
    try:
        proc = subprocess.run(
            ["dmesg"], capture_output=True, text=True, timeout=5
        )
    except Exception as exc:
        return {"available": False, "error": str(exc), "lines": []}
    if proc.returncode != 0:
        msg = (proc.stderr or "").strip() or "dmesg returned non-zero"
        hint = " (kernel.dmesg_restrict is on — try running as root)" if "perm" in msg.lower() or proc.returncode == 1 else ""
        return {"available": False, "error": msg + hint, "lines": []}

    low_tokens = [t.lower() for t in tokens if t]
    matched: List[str] = []
    for line in proc.stdout.splitlines():
        ll = line.lower()
        if not low_tokens or any(tok in ll for tok in low_tokens):
            matched.append(line)
    return {"available": True, "error": None, "lines": matched[-limit:]}


def usb_detail(sysfs_path: Optional[str], vid: Optional[str], pid: Optional[str],
               tty: Optional[str] = None) -> Dict[str, Any]:
    """Assemble a detail bundle for a USB device."""
    detail: Dict[str, Any] = {
        "sysfs_path": sysfs_path,
        "attrs": {},
        "interfaces": [],
        "driver": None,
        "dmesg": {"available": False, "error": "no sysfs path", "lines": []},
    }
    if sysfs_path and os.path.isdir(sysfs_path):
        detail["attrs"] = sysfs_attrs(sysfs_path)
        detail["interfaces"] = usb_interfaces(sysfs_path)
        drv_link = os.path.join(sysfs_path, "driver")
        if os.path.islink(drv_link):
            detail["driver"] = os.path.basename(os.path.realpath(drv_link))

    tokens = [t for t in [tty, (f"{vid}:{pid}" if vid and pid else None)] if t]
    detail["dmesg"] = dmesg_lines(tokens)
    return detail
