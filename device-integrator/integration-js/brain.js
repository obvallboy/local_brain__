"use strict";
// The integration brain in Node — thermostat control loop + data-integrity guard.
// Transport-neutral and dependency-free, so it is testable without any library
// or hardware. Mirror of integration/brain.py.

function defaultValidate(v) {
  return typeof v === "number" && Number.isFinite(v) && v >= -40 && v <= 85;
}

class Brain {
  constructor(cfg = {}) {
    this.hi = cfg.hi ?? 28;
    this.lo = cfg.lo ?? 24;
    this.integrity = cfg.integrity ?? true;
    this.validate = cfg.validate || defaultValidate;
    this.detector = cfg.detector ?? null;   // optional learned anomaly guard
    this.lastGood = cfg.lastGood ?? 22;
    this.ventOpen = false;
    this.alerts = [];
    this.rejected = 0;
    this.anomalies = 0;
    this._alerted = false;
    this._anomalyAlerted = false;
  }

  ingest(value, ts) {
    ts = ts ?? Date.now();
    const numeric = typeof value === "number" && Number.isFinite(value);
    // guard 1: integrity / plausible range
    if (this.integrity && !this.validate(value)) {
      this.rejected++;
      if (!this._alerted) {
        this.alerts.push({ t: ts, kind: "integrity", msg: `rejected reading ${JSON.stringify(value)}; holding ${this.lastGood}` });
        this._alerted = true;
      }
      return { accepted: false, used: this.lastGood };
    }
    // guard 2: learned anomaly (sees only numeric, in-range readings)
    if (this.detector && numeric) {
      const { anomaly, score } = this.detector.check(value);
      if (anomaly) {
        this.rejected++;
        this.anomalies++;
        if (!this._anomalyAlerted) {
          this.alerts.push({ t: ts, kind: "anomaly", msg: `in-range reading ${value} looks abnormal (z=${score.toFixed(1)}); holding ${this.lastGood}` });
          this._anomalyAlerted = true;
        }
        return { accepted: false, used: this.lastGood };
      }
    }
    if (numeric) {
      this.lastGood = value;
      this._alerted = false;
      this._anomalyAlerted = false;
      return { accepted: true, used: this.lastGood };
    }
    return { accepted: false, used: this.lastGood };
  }

  decide() {
    const cmds = [];
    if (this.lastGood >= this.hi && !this.ventOpen) {
      this.ventOpen = true;
      cmds.push({ device: "plc-01", action: "write_register", args: { register: 40001, value: 1 } });
    } else if (this.lastGood <= this.lo && this.ventOpen) {
      this.ventOpen = false;
      cmds.push({ device: "plc-01", action: "write_register", args: { register: 40001, value: 0 } });
    }
    return cmds;
  }

  step(value, ts) {
    this.ingest(value, ts);
    return this.decide();
  }
}

module.exports = { Brain, defaultValidate };
