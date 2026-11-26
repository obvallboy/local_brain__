from filecabinet.temp import RealNetwork, windows_gateway

IPCONFIG = """
Wireless LAN adapter Wi-Fi:

   Connection-specific DNS Suffix  . : home
   Link-local IPv6 Address . . . . . : fe80::1c2d:3e4f:5a6b:7c8d%12
   IPv4 Address. . . . . . . . . . . : 192.168.1.42
   Subnet Mask . . . . . . . . . . . : 255.255.255.0
   Default Gateway . . . . . . . . . : fe80::1%12
                                       192.168.1.1

Ethernet adapter Bluetooth Network Connection:

   Media State . . . . . . . . . . . : Media disconnected
"""


def test_windows_gateway_on_the_following_line():
    assert windows_gateway(IPCONFIG) == "192.168.1.1"


def test_windows_gateway_on_the_same_line():
    assert windows_gateway("   Default Gateway . . . . . . . . . : 10.0.0.1\n") == "10.0.0.1"


def test_windows_no_gateway():
    assert windows_gateway("   Default Gateway . . . . . . . . . :\n\n") is None


def test_real_network_never_raises():
    # Whatever this machine allows, each check returns a value or None (unknown).
    net = RealNetwork()
    for result in (net.interface_up(), net.gateway(), net.ping("127.0.0.1"), net.resolves("localhost")):
        assert result is None or isinstance(result, (bool, str))
