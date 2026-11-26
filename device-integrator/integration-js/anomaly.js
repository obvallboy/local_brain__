"use strict";
// A lightweight online anomaly detector — the "learned" third guard.
// Mirror of integration/anomaly.py. Learns normal telemetry with an
// exponentially weighted mean/variance, then scores each reading by how many
// standard deviations it sits from the expected value. It catches values that
// are *in range but abnormal for this sensor* (e.g. 45°C on a ~25°C sensor) —
// the kind of fault the fixed range check misses. Dependency-free.

class AnomalyDetector {
  constructor(cfg = {}) {
    this.warmup = cfg.warmup ?? 15;      // readings to learn "normal" before scoring
    this.threshold = cfg.threshold ?? 4; // z-score above which a reading is an anomaly
    this.alpha = cfg.alpha ?? 0.3;       // EW mean/variance smoothing (0..1)
    this.n = 0;
    this.mean = 0;
    this.var = 1;                        // EW variance (sane prior / no div-by-zero)
  }

  std() {
    return this.var > 0 ? Math.sqrt(this.var) : 0;
  }

  // Fold a trusted reading into the model (incremental EWMA mean/variance).
  update(x) {
    x = Number(x);
    this.n++;
    if (this.n === 1) { this.mean = x; return; }
    const diff = x - this.mean;
    const incr = this.alpha * diff;
    this.mean += incr;
    this.var = (1 - this.alpha) * (this.var + diff * incr);
  }

  // Robust z-score against the learned model (0 while warming up).
  score(x) {
    if (this.n < 2) return 0;
    const s = this.std();
    if (s < 1e-9) return Math.abs(x - this.mean) < 1e-9 ? 0 : Infinity;
    return Math.abs(x - this.mean) / s;
  }

  // Score a reading and, if it looks normal, learn from it. During warm-up it
  // always returns {anomaly:false, score:0} and learns. After warm-up a normal
  // reading is learned, an anomalous one is NOT (a spike never poisons the model).
  check(x) {
    if (this.n < this.warmup) {
      this.update(x);
      return { anomaly: false, score: 0 };
    }
    const score = this.score(x);
    const anomaly = score > this.threshold;
    if (!anomaly) this.update(x);
    return { anomaly, score };
  }
}

module.exports = { AnomalyDetector };
