import pytest

pytest.importorskip("pydantic")  # runs in CI where pydantic is installed

from integration.models import DeviceConfig, SensorReading, parse_reading  # noqa: E402


def test_valid_reading():
    r = SensorReading(device="temp-01", value=25.5)
    assert r.value == 25.5 and r.metric == "tempC"


def test_rejects_out_of_range():
    with pytest.raises(Exception):
        SensorReading(device="temp-01", value=999)
    with pytest.raises(Exception):
        SensorReading(device="temp-01", value=-300)


def test_parse_reading_none_on_corrupt():
    assert parse_reading({"device": "temp-01", "value": 999}) is None
    good = parse_reading({"device": "temp-01", "value": 25})
    assert good is not None and good.value == 25


def test_device_config_proto_pattern():
    DeviceConfig(name="plc-01", ip="10.0.0.22", proto="modbus")
    with pytest.raises(Exception):
        DeviceConfig(name="x", ip="10.0.0.9", proto="smtp")
