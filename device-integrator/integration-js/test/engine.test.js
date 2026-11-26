"use strict";
const test = require("node:test");
const assert = require("node:assert");
const { runSim } = require("../engine");

test("sim runs and controls the loop", () => {
  const { brain, log } = runSim(30);
  assert.equal(log.length, 30);
  const vents = new Set(log.map((e) => e.vent));
  assert.ok(vents.has(0) && vents.has(1)); // vent toggled
  assert.ok(brain.lastGood >= -40 && brain.lastGood <= 85);
});

test("sim fuzz with guard rejects and alerts", () => {
  const { brain } = runSim(30, 5, true);
  assert.ok(brain.rejected > 0);
  assert.ok(brain.alerts.some((a) => a.kind === "integrity"));
  assert.equal(typeof brain.lastGood, "number");
});

test("sim guard off rejects nothing", () => {
  const { brain } = runSim(20, 0, false);
  assert.equal(brain.rejected, 0);
});
