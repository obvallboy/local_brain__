"""Unit tests for the learned anomaly detector (stdlib only — no ML dependency)."""

import random

from integration.anomaly import AnomalyDetector


def _warm(det, value=25.0, jitter=0.1, seed=0):
    rng = random.Random(seed)
    for _ in range(det.warmup):
        det.check(value + rng.uniform(-jitter, jitter))


def test_warmup_learns_and_never_flags():
    det = AnomalyDetector(warmup=10)
    flagged = sum(det.check(25.0 + 0.1 * (i % 3))[0] for i in range(10))
    assert flagged == 0
    assert det.n == 10                      # every warm-up reading was learned
    assert 24.0 < det.mean < 26.0


def test_flags_a_clear_outlier_after_warmup():
    det = AnomalyDetector(warmup=12, threshold=4.0)
    _warm(det)
    is_anomaly, score = det.check(60.0)     # far from the learned ~25
    assert is_anomaly is True
    assert score > 4.0


def test_does_not_learn_from_an_anomaly():
    det = AnomalyDetector(warmup=12, threshold=4.0)
    _warm(det)
    n_before, mean_before = det.n, det.mean
    det.check(500.0)                         # anomaly must not move the baseline
    assert det.n == n_before
    assert det.mean == mean_before


def test_normal_reading_passes_and_is_learned():
    det = AnomalyDetector(warmup=12)
    _warm(det)
    n_before = det.n
    is_anomaly, _ = det.check(25.05)
    assert is_anomaly is False
    assert det.n == n_before + 1             # a trusted reading updates the model


def test_slow_drift_is_tracked_not_flagged():
    # A legitimate gradual rise (room warming) must not trip the detector.
    det = AnomalyDetector(warmup=12, threshold=4.0, alpha=0.3)
    value = 25.0
    for _ in range(det.warmup):
        value += 0.1
        det.check(value)
    flagged = 0
    for _ in range(30):
        value += 0.1
        flagged += det.check(value)[0]
    assert flagged == 0


def test_in_range_value_can_be_anomalous():
    # The whole point: a value well inside any plausible range is still caught
    # when it is abnormal for *this* sensor.
    det = AnomalyDetector(warmup=12, threshold=4.0)
    _warm(det)
    is_anomaly, _ = det.check(45.0)          # 45°C is "plausible" but not for a 25°C sensor
    assert is_anomaly is True
