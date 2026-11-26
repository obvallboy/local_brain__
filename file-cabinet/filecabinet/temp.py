"""The temp drawer: load the real thing so it can be seen instead of assumed.

Version 1 has one tool set, network diagnostics. Each check records what was
actually observed; a check that cannot run is recorded as unknown (None),
never guessed.
"""

from __future__ import annotations

import platform
import re
import shutil
import socket
import subprocess
from dataclasses import dataclass, field
from typing import Protocol


class NetworkTools(Protocol):
    def interface_up(self) -> bool | None: ...
    def gateway(self) -> str | None: ...
    def ping(self, host: str) -> bool | None: ...
    def resolves(self, name: str) -> bool | None: ...


def _run(cmd: list[str], timeout: float = 4.0) -> subprocess.CompletedProcess | None:
    if shutil.which(cmd[0]) is None:
        return None
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


WINDOWS = platform.system() == "Windows"
IPV4 = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")


def windows_gateway(ipconfig_output: str) -> str | None:
    """First IPv4 default gateway in English `ipconfig` output (it may sit on the line after the label)."""
    lines = ipconfig_output.splitlines()
    for i, line in enumerate(lines):
        if "Default Gateway" not in line:
            continue
        block = [line.split(":", 1)[1] if ":" in line else ""]
        for follow in lines[i + 1:]:
            if not follow.strip() or ". ." in follow:  # blank or the next labelled line
                break
            block.append(follow)
        for text in block:
            if match := IPV4.search(text):
                return match.group(1)
    return None


class RealNetwork:
    """Checks this machine's actual network. Linux uses `ip`; Windows uses `ipconfig`.
    Anything that cannot be checked is reported as unknown."""

    def interface_up(self) -> bool | None:
        if WINDOWS:
            out = _run(["ipconfig"])
            return None if out is None or out.returncode != 0 else "IPv4 Address" in out.stdout
        out = _run(["ip", "-o", "link", "show", "up"])
        if out is None or out.returncode != 0:
            return None
        lines = [line for line in out.stdout.splitlines() if " lo:" not in line]
        return bool(lines)

    def gateway(self) -> str | None:
        if WINDOWS:
            out = _run(["ipconfig"])
            return None if out is None or out.returncode != 0 else windows_gateway(out.stdout)
        out = _run(["ip", "route", "show", "default"])
        if out is None or out.returncode != 0:
            return None
        parts = out.stdout.split()
        return parts[parts.index("via") + 1] if "via" in parts else None

    def ping(self, host: str) -> bool | None:
        cmd = ["ping", "-n", "1", "-w", "2000", host] if WINDOWS else ["ping", "-c", "1", "-W", "2", host]
        out = _run(cmd)
        return None if out is None else out.returncode == 0

    def resolves(self, name: str) -> bool | None:
        socket.setdefaulttimeout(4)
        try:
            socket.getaddrinfo(name, 443)
            return True
        except socket.gaierror:
            return False
        except OSError:
            return None


@dataclass
class SimulatedNetwork:
    """A pretend network for tests and demos."""

    up: bool | None = True
    gateway_ip: str | None = "192.168.1.1"
    gateway_ok: bool | None = True
    internet_ok: bool | None = True
    dns_ok: bool | None = True

    def interface_up(self) -> bool | None:
        return self.up

    def gateway(self) -> str | None:
        return self.gateway_ip

    def ping(self, host: str) -> bool | None:
        return self.gateway_ok if host == self.gateway_ip else self.internet_ok

    def resolves(self, name: str) -> bool | None:
        return self.dns_ok


SCENARIOS = {
    "healthy": SimulatedNetwork(),
    "dns": SimulatedNetwork(dns_ok=False),
    "no-router": SimulatedNetwork(gateway_ok=False, internet_ok=False, dns_ok=False),
    "isp-down": SimulatedNetwork(internet_ok=False, dns_ok=False),
    "adapter-off": SimulatedNetwork(up=False, gateway_ip=None, gateway_ok=None, internet_ok=False, dns_ok=False),
}

DESCRIBE = {
    "interface_up": ("network adapter is on", "network adapter is off"),
    "gateway_reachable": ("router answers", "router does not answer"),
    "internet_ip_reachable": ("internet reachable by address", "internet not reachable by address"),
    "dns_ok": ("website names resolve", "website names do not resolve (DNS failing)"),
}


@dataclass
class TempDrawer:
    task: str
    observations: dict = field(default_factory=dict)
    gateway_address: str | None = None

    def load(self, tools: NetworkTools) -> None:
        self.observations["interface_up"] = tools.interface_up()
        self.gateway_address = tools.gateway()
        self.observations["gateway_reachable"] = tools.ping(self.gateway_address) if self.gateway_address else None
        self.observations["internet_ip_reachable"] = tools.ping("1.1.1.1")
        self.observations["dns_ok"] = tools.resolves("example.com")

    def known(self) -> dict:
        return {k: v for k, v in self.observations.items() if v is not None}

    def summary(self) -> list[str]:
        lines = []
        for key, value in self.observations.items():
            if value is None:
                lines.append(f"{key}: could not check")
            else:
                yes, no = DESCRIBE[key]
                lines.append(yes if value else no)
        if self.gateway_address:
            lines.append(f"router address {self.gateway_address}")
        return lines
