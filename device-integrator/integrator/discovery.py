"""Local device discovery.

Enumerates hardware attached to *this* machine: serial ports, USB devices,
storage/block devices and network interfaces. Every probe degrades
gracefully — if an optional library or a platform facility (``/sys``,
``lsusb``) is missing, that source is skipped and the rest still works.

All functions are read-only.
"""

from __future__ import annotations

import glob
import os
import platform
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional


# --------------------------------------------------------------------------
# Capability probing
# --------------------------------------------------------------------------
def _try_import(name: str):
    try:
        return __import__(name)
    except Exception:
        return None


def capabilities() -> Dict[str, Any]:
    """Report which optional back-ends are available on this machine."""
    caps = {
        "platform": platform.system(),
        "platform_release": platform.release(),
        "python": platform.python_version(),
        "pyserial": _try_import("serial") is not None,
        "pyusb": _try_import("usb") is not None,
        "psutil": _try_import("psutil") is not None,
        "sysfs": os.path.isdir("/sys/bus/usb/devices"),
        "lsusb": shutil.which("lsusb") is not None,
        "dmesg": shutil.which("dmesg") is not None,
    }
    return caps


# --------------------------------------------------------------------------
# Serial ports
# --------------------------------------------------------------------------
def _scan_serial_ports() -> List[Dict[str, Any]]:
    """List serial ports. Uses pyserial when available, otherwise globs the
    common Linux device nodes so dev boards still show up."""
    ports: List[Dict[str, Any]] = []
    serial = _try_import("serial")
    if serial is not None:
        try:
            from serial.tools import list_ports  # type: ignore

            for p in list_ports.comports():
                ports.append(
                    {
                        "device": p.device,
                        "name": p.name,
                        "description": (p.description or "").strip() or None,
                        "hwid": (p.hwid or "").strip() or None,
                        "vid": f"{p.vid:04x}" if p.vid is not None else None,
                        "pid": f"{p.pid:04x}" if p.pid is not None else None,
                        "manufacturer": p.manufacturer,
                        "product": p.product,
                        "serial_number": p.serial_number,
                        "source": "pyserial",
                    }
                )
            return ports
        except Exception:
            pass

    # Fallback: glob device nodes (Linux / macOS).
    seen = set()
    patterns = [
        "/dev/ttyUSB*",
        "/dev/ttyACM*",
        "/dev/ttyS*",
        "/dev/tty.*",
        "/dev/cu.*",
        "/dev/serial/by-id/*",
    ]
    for pattern in patterns:
        for dev in sorted(glob.glob(pattern)):
            real = os.path.realpath(dev)
            if real in seen:
                continue
            seen.add(real)
            ports.append(
                {
                    "device": dev,
                    "name": os.path.basename(dev),
                    "description": None,
                    "hwid": None,
                    "vid": None,
                    "pid": None,
                    "manufacturer": None,
                    "product": None,
                    "serial_number": None,
                    "source": "glob",
                }
            )
    return ports


_LEGACY_UART = re.compile(r"^ttyS\d+$")


def is_placeholder_port(port: Dict[str, Any]) -> bool:
    """True for the empty legacy UART nodes (/dev/ttyS0-31) Linux creates whether or not
    any hardware is behind them. A real onboard UART reports a hwid (e.g. PNP0501),
    and USB adapters show up as ttyUSB*/ttyACM* with a vid, so neither is hidden."""
    if not _LEGACY_UART.match(port.get("name") or os.path.basename(port.get("device") or "")):
        return False
    if port.get("vid"):
        return False
    return (port.get("hwid") or "n/a").strip().lower() in ("n/a", "")


def list_serial_ports() -> List[Dict[str, Any]]:
    """Serial ports, each flagged ``placeholder`` when it's an empty legacy UART node."""
    ports = _scan_serial_ports()
    for p in ports:
        p["placeholder"] = is_placeholder_port(p)
    return ports


# --------------------------------------------------------------------------
# USB devices
# --------------------------------------------------------------------------
_USB_CLASSES = {
    0x00: "Per-interface",
    0x01: "Audio",
    0x02: "Communications/CDC",
    0x03: "HID",
    0x05: "Physical",
    0x06: "Image",
    0x07: "Printer",
    0x08: "Mass storage",
    0x09: "Hub",
    0x0A: "CDC-Data",
    0x0B: "Smart card",
    0x0D: "Content security",
    0x0E: "Video",
    0x0F: "Personal healthcare",
    0x10: "Audio/Video",
    0xE0: "Wireless",
    0xEF: "Miscellaneous",
    0xFE: "Application specific",
    0xFF: "Vendor specific",
}


def _usb_key(vid: Optional[str], pid: Optional[str], serial: Optional[str],
             extra: str = "") -> str:
    return "usb:" + ":".join(x for x in (vid, pid, serial or extra) if x)


def _read_sysfs(path: str, name: str) -> Optional[str]:
    try:
        with open(os.path.join(path, name), "r", errors="replace") as fh:
            return fh.read().strip()
    except Exception:
        return None


def _list_usb_sysfs() -> List[Dict[str, Any]]:
    devices: List[Dict[str, Any]] = []
    base = "/sys/bus/usb/devices"
    if not os.path.isdir(base):
        return devices
    for entry in sorted(os.listdir(base)):
        # Real devices have an idVendor; interfaces (e.g. "1-1:1.0") do not.
        path = os.path.join(base, entry)
        vid = _read_sysfs(path, "idVendor")
        pid = _read_sysfs(path, "idProduct")
        if not vid or not pid:
            continue
        cls_raw = _read_sysfs(path, "bDeviceClass")
        try:
            cls_int = int(cls_raw, 16) if cls_raw else None
        except ValueError:
            cls_int = None
        devices.append(
            {
                "vid": vid.lower(),
                "pid": pid.lower(),
                "manufacturer": _read_sysfs(path, "manufacturer"),
                "product": _read_sysfs(path, "product"),
                "serial_number": _read_sysfs(path, "serial"),
                "bus": _read_sysfs(path, "busnum"),
                "address": _read_sysfs(path, "devnum"),
                "usb_version": _read_sysfs(path, "version"),
                "speed": _read_sysfs(path, "speed"),
                "device_class": cls_int,
                "device_class_name": _USB_CLASSES.get(cls_int) if cls_int is not None else None,
                "sysfs_path": path,
                "source": "sysfs",
            }
        )
    return devices


def _list_usb_pyusb() -> List[Dict[str, Any]]:
    usb = _try_import("usb")
    if usb is None:
        return []
    try:
        import usb.core  # type: ignore
        import usb.util  # type: ignore
    except Exception:
        return []
    devices: List[Dict[str, Any]] = []
    try:
        found = list(usb.core.find(find_all=True))
    except Exception:
        # No backend (libusb) installed, or no permission.
        return []
    for dev in found:
        def _string(idx):
            try:
                return usb.util.get_string(dev, idx) if idx else None
            except Exception:
                return None

        cls_int = getattr(dev, "bDeviceClass", None)
        devices.append(
            {
                "vid": f"{dev.idVendor:04x}",
                "pid": f"{dev.idProduct:04x}",
                "manufacturer": _string(getattr(dev, "iManufacturer", 0)),
                "product": _string(getattr(dev, "iProduct", 0)),
                "serial_number": _string(getattr(dev, "iSerialNumber", 0)),
                "bus": getattr(dev, "bus", None),
                "address": getattr(dev, "address", None),
                "usb_version": None,
                "speed": getattr(dev, "speed", None),
                "device_class": cls_int,
                "device_class_name": _USB_CLASSES.get(cls_int) if cls_int is not None else None,
                "sysfs_path": None,
                "source": "pyusb",
            }
        )
    return devices


_LSUSB_RE = re.compile(
    r"Bus (\d+) Device (\d+): ID ([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\s*(.*)"
)


def _list_usb_lsusb() -> List[Dict[str, Any]]:
    if shutil.which("lsusb") is None:
        return []
    try:
        out = subprocess.run(
            ["lsusb"], capture_output=True, text=True, timeout=5
        ).stdout
    except Exception:
        return []
    devices: List[Dict[str, Any]] = []
    for line in out.splitlines():
        m = _LSUSB_RE.match(line.strip())
        if not m:
            continue
        bus, addr, vid, pid, desc = m.groups()
        devices.append(
            {
                "vid": vid.lower(),
                "pid": pid.lower(),
                "manufacturer": None,
                "product": desc.strip() or None,
                "serial_number": None,
                "bus": bus,
                "address": addr,
                "usb_version": None,
                "speed": None,
                "device_class": None,
                "device_class_name": None,
                "sysfs_path": None,
                "source": "lsusb",
            }
        )
    return devices


def list_usb_devices() -> List[Dict[str, Any]]:
    """List USB devices, preferring the richest source available:
    sysfs (Linux) → pyusb → lsusb. Each entry gets a stable ``key``."""
    for provider in (_list_usb_sysfs, _list_usb_pyusb, _list_usb_lsusb):
        devices = provider()
        if devices:
            break
    else:
        devices = []

    for d in devices:
        d["key"] = _usb_key(
            d.get("vid"),
            d.get("pid"),
            d.get("serial_number"),
            extra=f"{d.get('bus')}-{d.get('address')}",
        )
    return devices


# --------------------------------------------------------------------------
# Storage / block devices
# --------------------------------------------------------------------------
def list_storage() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    psutil = _try_import("psutil")
    if psutil is not None:
        try:
            for part in psutil.disk_partitions(all=False):
                usage = None
                try:
                    u = psutil.disk_usage(part.mountpoint)
                    usage = {"total": u.total, "used": u.used, "free": u.free, "percent": u.percent}
                except Exception:
                    pass
                out.append(
                    {
                        "device": part.device,
                        "mountpoint": part.mountpoint,
                        "fstype": part.fstype,
                        "opts": part.opts,
                        "usage": usage,
                        "source": "psutil",
                    }
                )
            if out:
                return out
        except Exception:
            pass

    # Fallback: /sys/block (Linux).
    base = "/sys/block"
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            if name.startswith(("loop", "ram")):
                continue
            path = os.path.join(base, name)
            size_sectors = _read_sysfs(path, "size")
            size_bytes = int(size_sectors) * 512 if size_sectors and size_sectors.isdigit() else None
            out.append(
                {
                    "device": f"/dev/{name}",
                    "mountpoint": None,
                    "fstype": None,
                    "opts": None,
                    "usage": {"total": size_bytes} if size_bytes else None,
                    "model": _read_sysfs(path, "device/model"),
                    "removable": _read_sysfs(path, "removable"),
                    "source": "sysfs",
                }
            )
    return out


# --------------------------------------------------------------------------
# Network interfaces
# --------------------------------------------------------------------------
def list_network() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    psutil = _try_import("psutil")
    if psutil is not None:
        try:
            addrs = psutil.net_if_addrs()
            stats = psutil.net_if_stats()
            for iface, addr_list in addrs.items():
                entry = {
                    "name": iface,
                    "addresses": [
                        {"family": str(a.family), "address": a.address, "netmask": a.netmask}
                        for a in addr_list
                    ],
                    "is_up": getattr(stats.get(iface), "isup", None),
                    "speed_mbps": getattr(stats.get(iface), "speed", None),
                    "mtu": getattr(stats.get(iface), "mtu", None),
                    "source": "psutil",
                }
                out.append(entry)
            if out:
                return out
        except Exception:
            pass

    # Fallback: /sys/class/net (Linux).
    base = "/sys/class/net"
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            path = os.path.join(base, name)
            out.append(
                {
                    "name": name,
                    "addresses": [],
                    "mac": _read_sysfs(path, "address"),
                    "is_up": (_read_sysfs(path, "operstate") == "up"),
                    "mtu": _read_sysfs(path, "mtu"),
                    "source": "sysfs",
                }
            )
    return out


# --------------------------------------------------------------------------
# Aggregate snapshot
# --------------------------------------------------------------------------
def snapshot() -> Dict[str, Any]:
    """Full read-only picture of everything attached right now."""
    return {
        "capabilities": capabilities(),
        "serial": list_serial_ports(),
        "usb": list_usb_devices(),
        "storage": list_storage(),
        "network": list_network(),
    }
