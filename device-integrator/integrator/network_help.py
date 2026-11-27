"""Live network scanning for Devy: probe a host over Wi-Fi/LAN and say what it is.

Uses the File Cabinet's netscan logic with a real socket prober. This runs on the
Devy computer/Pi, which can reach your network; the phone just asks for the result.
Only probes hosts you point it at — your own devices.
"""

from __future__ import annotations

import socket

from integrator.assistant import import_filecabinet

# Ports that send a banner on their own (no request needed).
_TALKS_FIRST = {22, 21, 23}


def tcp_prober(timeout: float = 0.6):
    """Return a prober(host, port) -> (is_open, banner|None) using plain sockets."""
    def probe(host: str, port: int):
        try:
            with socket.create_connection((host, port), timeout=timeout) as s:
                s.settimeout(timeout)
                banner = None
                try:
                    if port in _TALKS_FIRST:
                        banner = s.recv(128).decode('latin-1', 'replace').strip()
                    elif port in (80, 8080):
                        s.sendall(b'HEAD / HTTP/1.0\r\n\r\n')
                        banner = s.recv(256).decode('latin-1', 'replace').strip()
                except OSError:
                    banner = None
                return True, banner or None
        except OSError:
            return False, None
    return probe


def scan(host: str, timeout: float = 0.6) -> dict:
    """Scan one host and return {host, open_ports, guess, steps, say}."""
    import_filecabinet()
    from filecabinet.netscan import report, scan_host

    result = scan_host(tcp_prober(timeout), host)
    return {
        'host': result.host,
        'open_ports': [p for p, _ in result.open_ports],
        'guess': result.guess,
        'steps': result.steps,
        'say': report(result),
    }
