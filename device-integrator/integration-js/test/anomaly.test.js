"use strict";
const test = require("node:test");
const assert = require("node:assert");
const { AnomalyDetector } = require("../anomaly");
const { Brain } = require("../brain");
const { runSim } = require("../engine");

function warm(det, value = 25, jitter = 0.1) {
  for (let i = 0; i < det.warmup; i++) det.check(value + (i % 2 ? jitter : -jitter));
}

test("warm-up learns and never flags", () => {
  const det = new AnomalyDetector({ warmup: 10 });
  let flagged = 0;
  for (let i = 0; i < 10; i++) flagged += det.check(25 + 0.1 * (i % 3)).anomaly ? 1 : 0;
  assert.equal(flagged, 0);
  assert.equal(det.n, 10);
});

test("flags a clear outlier after warm-up", () => {
  const det = new AnomalyDetector({ warmup: 12, threshold: 4 });
  warm(det);
  const { anomaly, score } = det.check(60);
  assert.equal(anomaly, true);
  assert.ok(score > 4);
});

test("does not learn from an anomaly", () => {
  const det = new AnomalyDetector({ warmup: 12, threshold: 4 });
  warm(det);
  const nBefore = det.n, meanBefore = det.mean;
  det.check(500);
  assert.equal(det.n, nBefore);
  assert.equal(det.mean, meanBefore);
});

test("an in-range value can still be anomalous", () => {
  const det = new AnomalyDetector({ warmup: 12, threshold: 4 });
  warm(det);
  assert.equal(det.check(45).anomaly, true);   // 45°C is "plausible" but not for a 25°C sensor
});

test("slow drift is tracked, not flagged", () => {
  const det = new AnomalyDetector({ warmup: 12, threshold: 4, alpha: 0.3 });
  let v = 25;
  for (let i = 0; i < 12; i++) { v += 0.1; det.check(v); }
  let flagged = 0;
  for (let i = 0; i < 30; i++) { v += 0.1; flagged += det.check(v).anomaly ? 1 : 0; }
  assert.equal(flagged, 0);
});

test("brain catches an in-range glitch with the detector", () => {
  const b = new Brain({ detector: new AnomalyDetector({ warmup: 5, threshold: 4 }) });
  for (const v of [25, 25.2, 24.8, 25.1, 24.9, 25]) b.ingest(v);  // warm + 1
  const r = b.ingest(45);
  assert.equal(r.accepted, false);
  assert.equal(b.anomalies, 1);
  assert.ok(b.alerts.some((a) => a.kind === "anomaly"));
});

test("engine: in-range anomaly caught with guard, fools brain without it", () => {
  const withGuard = runSim(30, null, true, true, 20);
  assert.ok(withGuard.brain.anomalies >= 1);
  assert.equal(withGuard.log.find((e) => e.tick === 20).accepted, false);

  const without = runSim(30, null, true, false, 20);
  assert.equal(without.brain.anomalies, 0);
  assert.equal(without.log.find((e) => e.tick === 20).accepted, true);
});
