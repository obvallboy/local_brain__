"use strict";
const test = require("node:test");
const assert = require("node:assert");

// crypto-js may not be installed locally; the test skips there and runs in CI.
let security = null;
try { security = require("../security"); } catch (_) { security = null; }

test("hmac sign/verify roundtrip", (t) => {
  if (!security) return t.skip("crypto-js not installed");
  const key = "a-shared-device-key";
  const msg = '{"device":"temp-01","tempC":25.4}';
  const sig = security.sign(key, msg);
  assert.equal(security.verify(key, msg, sig), true);
});

test("tampered message or wrong key fails", (t) => {
  if (!security) return t.skip("crypto-js not installed");
  const key = "a-shared-device-key";
  const sig = security.sign(key, '{"tempC":25.4}');
  assert.equal(security.verify(key, '{"tempC":999.0}', sig), false);
  assert.equal(security.verify("the-wrong-key", '{"tempC":25.4}', sig), false);
});
