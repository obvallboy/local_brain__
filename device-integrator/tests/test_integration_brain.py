from integration.brain import Brain, BrainConfig


def test_thermostat_opens_and_closes():
    b = Brain()
    for v in [25, 26, 27, 28]:
        b.step(v)
    assert b.vent_open is True            # opened at >= 28
    for v in [26, 25, 24]:
        b.step(v)
    assert b.vent_open is False           # closed at <= 24


def test_rejects_corrupt_and_holds_last_good():
    b = Brain()
    b.ingest(25)
    accepted, used = b.ingest(999)
    assert accepted is False and used == 25 and b.last_good == 25 and b.rejected == 1
    assert any(a["kind"] == "integrity" for a in b.alerts)


def test_non_number_does_not_crash():
    b = Brain()
    b.ingest(25)
    for bad in ["0x8F3A", float("nan"), float("inf"), None, True]:
        accepted, used = b.ingest(bad)
        assert accepted is False and b.last_good == 25


def test_corrupt_never_opens_vent():
    b = Brain()
    b.ingest(25)
    for _ in range(6):
        b.step(999)
    assert b.vent_open is False           # never acted on garbage
    assert b.rejected == 6


def test_guard_off_is_fooled():
    b = Brain(BrainConfig(integrity=False))
    b.ingest(25)
    b.step(999)
    assert b.last_good == 999 and b.vent_open is True   # fooled: opened on garbage


def test_alert_fires_once_per_burst():
    b = Brain()
    b.ingest(25)
    for _ in range(4):
        b.ingest(999)
    integrity_alerts = [a for a in b.alerts if a["kind"] == "integrity"]
    assert len(integrity_alerts) == 1 and b.rejected == 4
