from integration.engine import run_sim


def test_sim_runs_and_controls_the_loop():
    brain, log = run_sim(ticks=30)
    assert len(log) == 30
    vents = {e["vent"] for e in log}
    assert 1 in vents and 0 in vents            # vent toggled during the run
    assert -40.0 <= brain.last_good <= 85.0


def test_sim_fuzz_with_guard_rejects_and_alerts():
    brain, log = run_sim(ticks=30, fuzz_after=5, integrity=True)
    assert brain.rejected > 0
    assert any(a["kind"] == "integrity" for a in brain.alerts)
    # engine never crashed on the corrupt stream
    assert isinstance(brain.last_good, float)


def test_sim_guard_off_can_be_fooled():
    # With both guards off and corrupt data, nothing is rejected.
    brain, log = run_sim(ticks=20, fuzz_after=0, integrity=False, anomaly=False)
    assert brain.rejected == 0                  # nothing rejected when guards off


def test_in_range_anomaly_is_caught_by_learned_guard():
    # 45°C passes the range/integrity check but is abnormal for this sensor;
    # only the learned anomaly guard catches it.
    brain, log = run_sim(ticks=30, anomaly_at=20, integrity=True, anomaly=True)
    assert brain.anomalies >= 1
    assert any(a["kind"] == "anomaly" for a in brain.alerts)
    spike = next(e for e in log if e["tick"] == 20)
    assert spike["reading"] == 45.0
    assert spike["accepted"] is False           # held last-good, did not act on the glitch
    assert brain.last_good < 40.0               # the 45°C spike was never absorbed


def test_in_range_anomaly_fools_brain_without_the_guard():
    # Same glitch, anomaly guard off: it passes the range check and is acted on.
    brain, log = run_sim(ticks=30, anomaly_at=20, integrity=True, anomaly=False)
    assert brain.anomalies == 0
    spike = next(e for e in log if e["tick"] == 20)
    assert spike["accepted"] is True            # the in-range glitch fooled the brain
