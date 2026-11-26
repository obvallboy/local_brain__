"use strict";
// Transports: an in-memory simulator plus real-library adapters.
// SimTransport needs nothing. The real adapters require their library lazily
// (inside the constructor), so this module loads with no dependencies installed
// and only pulls mqtt / axios / johnny-five when you actually use them.

class SimTransport {
  constructor(fuzz = false) {
    this.temp = 22;
    this.vent = 0;
    this.fuzz = fuzz;
  }
  readSensor() {
    const drift = this.vent === 1 ? -0.9 : 0.8;          // vent cools, closed heats
    this.temp = Math.round((this.temp + drift + (Math.random() - 0.5) * 0.3) * 10) / 10;
    if (this.fuzz) return [999, NaN, -273.1, 1500, "0x8F3A"][Math.floor(Math.random() * 5)];
    return this.temp;
  }
  writeRegister(reg, val) { if (reg === 40001) this.vent = val; return true; }
  pollCamera() { return { online: true, res: "1920x1080" }; }
}

// Real MQTT telemetry via `mqtt`.
class MqttTransport {
  constructor(opts = {}) {
    const mqtt = require("mqtt"); // lazy
    this.topic = opts.topic || "site/temp";
    this._last = null;
    this.client = mqtt.connect(opts.url || "mqtt://localhost:1883");
    this.client.on("connect", () => this.client.subscribe(this.topic));
    this.client.on("message", (_t, p) => { try { this._last = JSON.parse(p.toString()); } catch (_) { this._last = null; } });
  }
  readSensor() { return this._last ? this._last.tempC : undefined; }
}

// Real HTTP/REST camera via `axios`.
class HttpTransport {
  constructor(base = "http://camera.local") {
    this.axios = require("axios"); // lazy
    this.base = base;
  }
  async pollCamera() {
    const r = await this.axios.get(this.base + "/api/status", { timeout: 3000 });
    return r.data;
  }
}

// Real board/Arduino GPIO via `johnny-five` (the vent on a pin).
class BoardTransport {
  constructor(opts = {}) {
    const five = require("johnny-five"); // lazy
    this.pin = opts.pin || 13;
    this.board = new five.Board(opts);
    this.board.on("ready", () => { this.led = new five.Led(this.pin); });
  }
  writeRegister(reg, val) { if (reg === 40001 && this.led) { val ? this.led.on() : this.led.off(); } return true; }
}

module.exports = { SimTransport, MqttTransport, HttpTransport, BoardTransport };
