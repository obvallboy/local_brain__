"""Recognize a device on your Wi-Fi from its open ports and banners.

Unlike a bare chip, networked devices (ESP32s, routers, cameras, Pis) can be reached
over the air. This looks at which TCP ports a host has open, and any banner it sends,
and says what it probably is and how to reach it — honestly, with "unrecognized" when
it can't tell.

Probing a real host is injected (a callable (host, port) -> (open, banner)), so the
logic is testable without a network; the Device Integrator supplies a socket prober.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

# port -> (service name, how to reach it)
SERVICES: dict[int, tuple[str, str]] = {
    22: ('SSH', 'connect with  ssh user@HOST'),
    23: ('Telnet', 'open a console with  telnet HOST  (unencrypted — common on routers/embedded)'),
    80: ('HTTP (web UI)', 'open  http://HOST  in a browser'),
    443: ('HTTPS (web UI)', 'open  https://HOST  in a browser'),
    8080: ('HTTP-alt (web UI)', 'open  http://HOST:8080'),
    1883: ('MQTT', 'an IoT message broker — connect an MQTT client to HOST:1883'),
    8883: ('MQTT over TLS', 'an IoT message broker (TLS) on HOST:8883'),
    3232: ('Arduino/ESP OTA', 'flash it over Wi-Fi with espota / the Arduino IDE network port'),
    554: ('RTSP', 'a camera video stream — open  rtsp://HOST:554  in VLC'),
    9100: ('Raw print (JetDirect)', 'a network printer'),
    5555: ('ADB', 'an Android device/TV — adb connect HOST:5555'),
    445: ('SMB', 'Windows/file sharing'),
    139: ('SMB', 'Windows/file sharing'),
    21: ('FTP', 'connect with an FTP client'),
    53: ('DNS', 'a DNS server (often a router)'),
}

# Common ports worth probing, in a sensible order.
COMMON_PORTS = (80, 443, 22, 23, 3232, 1883, 8080, 554, 9100, 5555, 8883, 445, 139, 21, 53)

# A prober: given host and port, return (is_open, banner-or-None).
Prober = Callable[[str, int], tuple]


@dataclass
class NetScan:
    host: str
    open_ports: list = field(default_factory=list)   # [(port, banner|None)]
    guess: Optional[str] = None                       # best device-type guess
    steps: list = field(default_factory=list)         # how to reach it


def scan_host(prober: Prober, host: str, ports=COMMON_PORTS) -> NetScan:
    result = NetScan(host)
    banners: dict[int, str] = {}
    for port in ports:
        try:
            is_open, banner = prober(host, port)
        except Exception:
            is_open, banner = False, None
        if is_open:
            result.open_ports.append((port, banner))
            if banner:
                banners[port] = banner
    result.guess = classify([p for p, _ in result.open_ports], banners)
    result.steps = [SERVICES[p][1].replace('HOST', host) for p, _ in result.open_ports if p in SERVICES]
    return result


def classify(open_ports, banners: Optional[dict] = None) -> Optional[str]:
    """A best-guess device type from the ports and banners. None if nothing stands out."""
    banners = banners or {}
    ports = set(open_ports)
    text = ' '.join(banners.values()).lower()

    if 3232 in ports or 'esp' in text or 'arduino' in text or 'lwip' in text:
        return 'an ESP32/ESP8266 or Arduino board (you can likely flash it over Wi-Fi)'
    if 554 in ports or 9100 in ports:
        return 'a camera' if 554 in ports else 'a network printer'
    if 5555 in ports:
        return 'an Android device or TV'
    if 'dropbear' in text or (23 in ports and 53 in ports) or (80 in ports and 53 in ports):
        return 'a router or embedded Linux device'
    if 445 in ports or 139 in ports:
        return 'a Windows PC or file server'
    if 'openssh' in text and 22 in ports:
        return 'a Linux computer or Raspberry Pi'
    if 22 in ports:
        return 'a Linux/Unix host'
    if ports & {80, 443, 8080}:
        return 'something with a web interface'
    return None


def report(scan: NetScan) -> str:
    if not scan.open_ports:
        return (f"{scan.host} didn't answer on the common ports. It may be off, firewalled, or not at that "
                "address. (A device can be online and still show nothing here.)")
    named = ', '.join(f"{p} ({SERVICES[p][0]})" if p in SERVICES else str(p) for p, _ in scan.open_ports)
    head = f"{scan.host} is up. Open: {named}."
    if scan.guess:
        head += f" Looks like {scan.guess}."
    if scan.steps:
        head += ' You can ' + '; '.join(scan.steps[:3]) + '.'
    return head
