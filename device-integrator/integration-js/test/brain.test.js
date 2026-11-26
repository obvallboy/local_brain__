"use strict";
const test = require("node:test");
const assert = require("node:assert");
const { Brain } = require("../brain");

test("thermostat opens and closes", () => {
  const b = new Brain();
  [25, 26, 27, 28].forEach((v) => b.step(v));
  assert.equal(b.ventOpen, true);
  [26, 25, 24].forEach((v) => b.step(v));
  assert.equal(b.ventOpen, false);
});

test("rejects corrupt and holds last-good", () => {
  const b = new Brain();
  b.ingest(25);
  const r = b.ingest(999);
  assert.equal(r.accepted, false);
  assert.equal(r.used, 25);
  assert.equal(b.lastGood, 25);
  assert.equal(b.rejected, 1);
  assert.ok(b.alerts.some((a) => a.kind === "integrity"));
});

test("non-number does not crash", () => {
  const b = new Brain();
  b.ingest(25);
  for (const bad of ["0x8F3A", NaN, Infinity, null, true, undefined]) {
    const r = b.ingest(bad);
    assert.equal(r.accepted, false);
    assert.equal(b.lastGood, 25);
  }
});

test("corrupt never opens the vent", () => {
  const b = new Brain();
  b.ingest(25);
  for (let i = 0; i < 6; i++) b.step(999);
  assert.equal(b.ventOpen, false);
  assert.equal(b.rejected, 6);
});

test("guard off is fooled", () => {
  const b = new Brain({ integrity: false });
  b.ingest(25);
  b.step(999);
  assert.equal(b.lastGood, 999);
  assert.equal(b.ventOpen, true);
});

test("integrity alert fires once per burst", () => {
  const b = new Brain();
  b.ingest(25);
  for (let i = 0; i < 4; i++) b.ingest(999);
  assert.equal(b.alerts.filter((a) => a.kind === "integrity").length, 1);
  assert.equal(b.rejected, 4);
});
