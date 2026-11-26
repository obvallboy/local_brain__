"""Temp drawer, tool set 2: the hardware attached to this machine.

The host app supplies a snapshot of what is plugged in right now (the Device
Integrator's discovery) and the names you gave devices in its Notes. Answers are
built only from that snapshot and labelled "I checked"; nothing is assumed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .similarity import Matcher, tokens

DEVICE_QUESTION = re.compile(
    r"\b(plugged in|plugged into|attached|usb|serial ports?|com ?ports?|com\d+|tty\w*|devices?|"
    r"dev ?board|arduino|esp32|esp8266|raspberry pi|pi pico|microcontroller|showing up|detected|"
    r"recogni[sz]ed|connected to (this|the|my) (computer|laptop|pc|desktop|machine))\b",
    re.I,
)

# Words about the act of checking, not about which device.
META = set(tokens(
    "plugged plug in into attached attach connected connect usb serial port ports com device devices see "
    "show showing up detected detect recognized recognised there any what which list computer laptop pc "
    "desktop machine right now currently anything everything thing things this"
))


@dataclass(frozen=True)
class Device:
    kind: str   # serial | usb | storage | network
    name: str   # your label first, then what the device calls itself
    where: str  # port, bus address, mount point or address
    text: str   # everything searchable about it
    noise: bool = False  # hubs and the like: searchable, left out of summaries


def _clean(value):
    """Drop placeholder values such as pyserial's "n/a" for unnamed built-in ports."""
    return None if value is None or str(value).strip().lower() in ("", "n/a", "none", "unknown") else value


def _join(*parts) -> str:
    return " ".join(str(p) for p in parts if _clean(p))


def build(snapshot: dict, labels: dict | None = None) -> list[Device]:
    labels = labels or {}
    out = []
    for d in snapshot.get("serial") or []:
        key = d.get("key") or "serial:" + str(d.get("device") or d.get("name") or "")
        note = labels.get(key) or {}
        name = note.get("label") or _clean(d.get("description")) or _clean(d.get("product")) or d.get("device") or "serial port"
        vidpid = f"{d.get('vid')}:{d.get('pid')}" if d.get("vid") else ""
        out.append(Device("serial", name, d.get("device") or "", _join(
            note.get("label"), note.get("note"), d.get("description"), d.get("manufacturer"),
            d.get("product"), d.get("device"), vidpid)))
    for d in snapshot.get("usb") or []:
        key = d.get("key") or f"usb:{d.get('vid')}:{d.get('pid')}"
        note = labels.get(key) or {}
        name = note.get("label") or d.get("product") or d.get("manufacturer") or f"{d.get('vid')}:{d.get('pid')}"
        where = f"USB bus {d.get('bus')}, address {d.get('address')}" if d.get("bus") else f"USB {d.get('vid')}:{d.get('pid')}"
        noise = (d.get("device_class_name") or "").lower() == "hub" or "hub" in (d.get("product") or "").lower()
        out.append(Device("usb", name, where, _join(
            note.get("label"), note.get("note"), d.get("product"), d.get("manufacturer"),
            d.get("device_class_name"), f"{d.get('vid')}:{d.get('pid')}", d.get("serial_number")), noise))
    for d in snapshot.get("storage") or []:
        out.append(Device("storage", d.get("device") or "disk", d.get("mountpoint") or "",
                          _join(d.get("device"), d.get("mountpoint"), d.get("fstype"))))
    for d in snapshot.get("network") or []:
        if d.get("is_up") is False:
            continue
        addr = next((a.get("address") for a in d.get("addresses") or [] if a.get("address")), "")
        out.append(Device("network", d.get("name") or "interface", addr, _join(d.get("name"), addr, d.get("mac"))))
    return out


_GROUPS = [("serial", "serial port", "serial ports"), ("usb", "USB device", "USB devices"),
           ("storage", "storage device", "storage devices"), ("network", "network interface up", "network interfaces up")]


def summarize(devices: list[Device], names_per_group: int = 4) -> str:
    parts = []
    for kind, one, many in _GROUPS:
        group = [d for d in devices if d.kind == kind and not d.noise]
        if not group:
            continue
        label = one if len(group) == 1 else many
        if kind in ("serial", "usb"):
            shown = [f"{d.name} on {d.where}" if kind == "serial" and d.where and d.where != d.name else d.name
                     for d in group[:names_per_group]]
            more = f", +{len(group) - names_per_group} more" if len(group) > names_per_group else ""
            parts.append(f"{len(group)} {label} ({', '.join(shown)}{more})")
        else:
            parts.append(f"{len(group)} {label}")
    return "; ".join(parts) if parts else "nothing attached that I can see"


def find(devices: list[Device], terms: set[str], matcher: Matcher | None = None) -> list[Device]:
    """Devices that match at least half of the asked-about words (by meaning, if an embedder is set)."""
    matcher = matcher or Matcher()
    if not terms:
        return []
    return [d for d in devices if matcher.overlap(terms, d.text) >= 0.5]


def query_terms(question: str) -> set[str]:
    return set(tokens(question)) - META
