import os

from integrator import discovery, details


def test_capabilities_shape():
    caps = discovery.capabilities()
    assert "platform" in caps
    for key in ("pyserial", "pyusb", "psutil", "sysfs", "lsusb", "dmesg"):
        assert isinstance(caps[key], bool)


def test_snapshot_shape():
    snap = discovery.snapshot()
    assert set(snap) == {"capabilities", "serial", "usb", "storage", "network"}
    for key in ("serial", "usb", "storage", "network"):
        assert isinstance(snap[key], list)


def test_usb_devices_have_keys():
    for d in discovery.list_usb_devices():
        assert d["key"].startswith("usb:")
        assert "vid" in d and "pid" in d


def test_list_functions_never_raise():
    # These must degrade gracefully on any platform / with no hardware.
    assert isinstance(discovery.list_serial_ports(), list)
    assert isinstance(discovery.list_storage(), list)
    assert isinstance(discovery.list_network(), list)


def test_sysfs_attrs_reads_fixture(tmp_path):
    d = tmp_path / "1-1"
    d.mkdir()
    (d / "idVendor").write_text("10c4\n")
    (d / "idProduct").write_text("ea60\n")
    (d / "product").write_text("CP2102 USB to UART\n")
    (d / "empty").write_text("")  # should be skipped

    attrs = details.sysfs_attrs(str(d), ["idVendor", "idProduct", "product", "empty", "missing"])
    assert attrs["idVendor"] == "10c4"
    assert attrs["idProduct"] == "ea60"
    assert attrs["product"] == "CP2102 USB to UART"
    assert "empty" not in attrs
    assert "missing" not in attrs


def test_usb_interfaces_from_fixture(tmp_path):
    dev = tmp_path / "1-1"
    dev.mkdir()
    (dev / "idVendor").write_text("10c4")
    iface = tmp_path / "1-1" / "1-1:1.0"
    iface.mkdir()
    (iface / "bInterfaceNumber").write_text("00")
    (iface / "bInterfaceClass").write_text("ff")
    (iface / "bNumEndpoints").write_text("02")

    ifaces = details.usb_interfaces(str(dev))
    assert len(ifaces) == 1
    assert ifaces[0]["bInterfaceClass"] == "ff"
    assert ifaces[0]["interface"] == "1-1:1.0"


def test_dmesg_handles_missing_binary(monkeypatch):
    monkeypatch.setattr(details.shutil, "which", lambda _: None)
    res = details.dmesg_lines(["ttyUSB0"])
    assert res["available"] is False
    assert res["lines"] == []


def test_usb_detail_bad_path_is_safe():
    detail = details.usb_detail("/does/not/exist", "10c4", "ea60", tty="ttyUSB0")
    assert detail["attrs"] == {}
    assert detail["interfaces"] == []
