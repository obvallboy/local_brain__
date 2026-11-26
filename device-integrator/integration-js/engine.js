"use strict";
// Integration engine (Node): wires a transport + the brain into a loop.
// Run against the simulator with no deps/hardware:
//   node engine.js --sim --ticks 24 --fuzz-after 8

const { Brain } = require("./brain");
const { AnomalyDetector } = require("./anomaly");
const { SimTransport } = require("./transports");

// fuzzAfter injects out-of-range corrupt data (integrity guard catches it);
// anomalyAt injects one in-range 45°C glitch (only the anomaly guard catches it).
function runSim(ticks = 24, fuzzAfter = null, integrity = true, anomaly = true, anomalyAt = null) {
  const t = new SimTransport();
  const detector = anomaly ? new AnomalyDetector() : null;
  const brain = new Brain({ integrity, detector });
  const log = [];
  for (let i = 0; i < ticks; i++) {
    if (fuzzAfter != null && i === fuzzAfter) t.fuzz = true;
    let reading = t.readSensor();
    if (anomalyAt != null && i === anomalyAt) reading = 45.0;  // in range, abnormal for this sensor
    const { accepted, used } = brain.ingest(reading);
    for (const c of brain.decide()) {
      if (c.action === "write_register") t.writeRegister(c.args.register, c.args.value);
    }
    log.push({ tick: i, reading, used, accepted, vent: t.vent });
  }
  return { brain, log };
}

function main(argv) {
  if (!argv.includes("--sim")) {
    console.log("Run with --sim. For real devices, use the adapters in transports.js.");
    return;
  }
  const num = (flag, def) => { const i = argv.indexOf(flag); return i >= 0 ? Number(argv[i + 1]) : def; };
  const ticks = num("--ticks", 24);
  const fuzzAfter = argv.includes("--fuzz-after") ? num("--fuzz-after", null) : null;
  const anomalyAt = argv.includes("--anomaly-at") ? num("--anomaly-at", null) : null;
  const integrity = !argv.includes("--no-integrity");
  const anomaly = !argv.includes("--no-anomaly");
  const { brain, log } = runSim(ticks, fuzzAfter, integrity, anomaly, anomalyAt);
  for (const e of log) {
    const mark = e.accepted ? "" : "   << REJECTED (held last-good)";
    console.log(`t${String(e.tick).padStart(2)}  reading=${String(e.reading).padStart(8)}  used=${String(e.used).padStart(5)}C  vent=${e.vent ? "OPEN" : "closed"}${mark}`);
  }
  console.log(`\nrejected=${brain.rejected}  (anomalies=${brain.anomalies})  alerts=${brain.alerts.length}  integrity=${integrity ? "ON" : "OFF"}  anomaly=${anomaly ? "ON" : "OFF"}  final_vent=${brain.ventOpen ? "OPEN" : "closed"}`);
  for (const a of brain.alerts) console.log(`  ! ${a.kind}: ${a.msg}`);
}

if (require.main === module) main(process.argv.slice(2));
module.exports = { runSim };
