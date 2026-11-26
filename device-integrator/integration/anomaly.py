"""A lightweight online anomaly detector — the "learned" third guard.

It learns the normal behaviour of a telemetry stream with an exponentially
weighted mean and variance, then scores each new reading by how many standard
deviations it sits from the expected value. A reading above the threshold is
flagged as an anomaly.

Why it matters for troubleshooting: the integrity guard only catches values
*out of range* (999 °C). This catches values that are *in range but abnormal for
this sensor* — e.g. a jump to 45 °C on a sensor that normally sits at 25 ±2 —
which is exactly the kind of fault a fixed threshold misses.

The EW mean/variance is deliberately adaptive: it tracks slow, legitimate drift
(a room warming over the day) so it does not cry wolf, while a sudden jump still
stands out. Pure stdlib (no ML dependency) so it runs and tests anywhere; it's
the simplest honest form of the anomaly detection the ML/MLOps roadmaps scale up
(isolation forests, autoencoders). The interface (`check` → `(is_anomaly, score)`)
stays the same if you swap the internals for a trained model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class AnomalyDetector:
    warmup: int = 15           # readings to learn "normal" before it starts scoring
    threshold: float = 4.0     # z-score above which a reading is an anomaly
    alpha: float = 0.3         # smoothing for the EW mean/variance (0..1; higher = faster)

    n: int = 0
    mean: float = 0.0
    var: float = 1.0           # EW variance (starts at 1 as a sane prior / no div-by-zero)

    def std(self) -> float:
        return math.sqrt(self.var) if self.var > 0 else 0.0

    def update(self, x: float) -> None:
        """Fold a reading into the learned model. Call only on readings you trust.

        Uses the standard incremental EWMA mean/variance (diff taken against the
        *old* mean): mean += a·diff ; var = (1-a)·(var + a·diff²)."""
        x = float(x)
        self.n += 1
        if self.n == 1:
            self.mean = x
            return
        diff = x - self.mean
        incr = self.alpha * diff
        self.mean += incr
        self.var = (1.0 - self.alpha) * (self.var + diff * incr)

    def score(self, x: float) -> float:
        """Robust z-score of x against the learned model (0 while warming up)."""
        if self.n < 2:
            return 0.0
        s = self.std()
        if s < 1e-9:
            return 0.0 if abs(x - self.mean) < 1e-9 else float("inf")
        return abs(x - self.mean) / s

    def check(self, x: float) -> tuple[bool, float]:
        """Score a reading and, if it looks normal, learn from it.

        During warm-up it always returns ``(False, 0.0)`` and learns. After warm-up
        it scores first; a normal reading is learned, an anomalous one is NOT (so a
        spike never poisons the baseline). Returns ``(is_anomaly, score)``."""
        if self.n < self.warmup:
            self.update(x)
            return (False, 0.0)
        sc = self.score(x)
        is_anomaly = sc > self.threshold
        if not is_anomaly:
            self.update(x)
        return (is_anomaly, sc)
