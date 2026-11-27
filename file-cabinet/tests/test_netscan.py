"""Recognize a device on the network from its open ports and banners."""

from filecabinet.netscan import classify, report, scan_host


def fake_prober(open_map):
    """open_map: {port: banner-or-True}. Any port not listed is closed."""
    def prober(host, port):
        if port in open_map:
            b = open_map[port]
            return True, (b if isinstance(b, str) else None)
        return False, None
    return prober


def test_esp_by_ota_port():
    scan = scan_host(fake_prober({80: 'Server: ESP8266', 3232: True}), '192.168.1.50')
    assert 'ESP' in (scan.guess or '')
    assert any('espota' in s or 'flash it over Wi-Fi' in s for s in scan.steps)
    assert '192.168.1.50' in report(scan) and 'web interface' not in report(scan)


def test_linux_box_by_ssh_banner():
    scan = scan_host(fake_prober({22: 'SSH-2.0-OpenSSH_9.6', 80: True}), 'host')
    assert 'Linux' in (scan.guess or '')
    assert 'ssh user@host' in report(scan)


def test_camera_and_printer():
    assert classify([554]) == 'a camera'
    assert classify([9100]) == 'a network printer'


def test_router_guess():
    assert 'router' in (classify([23, 53], {23: 'dropbear'}) or '')


def test_web_only_is_vague_but_honest():
    scan = scan_host(fake_prober({80: True}), 'h')
    assert scan.guess == 'something with a web interface'
    assert 'http://h' in report(scan)


def test_nothing_open_is_reported_not_guessed():
    scan = scan_host(fake_prober({}), '10.0.0.9')
    assert scan.open_ports == [] and scan.guess is None
    assert "didn't answer" in report(scan)


def test_unknown_ports_dont_crash():
    scan = scan_host(fake_prober({9999: True}), 'h')
    assert scan.open_ports == []  # 9999 isn't in COMMON_PORTS, so it isn't probed
