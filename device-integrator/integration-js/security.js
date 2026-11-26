"use strict";
// Signed telemetry with crypto-js (HMAC-SHA256). Devices sign messages; the
// engine rejects anything tampered. Same scheme the Device Bench uses in-browser.

const CryptoJS = require("crypto-js");

function sign(key, message) {
  return CryptoJS.HmacSHA256(String(message), String(key)).toString(CryptoJS.enc.Hex);
}

function verify(key, message, signature) {
  const expected = sign(key, message);
  const got = String(signature);
  if (expected.length !== got.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i++) diff |= expected.charCodeAt(i) ^ got.charCodeAt(i);
  return diff === 0; // constant-time-ish compare
}

module.exports = { sign, verify };
