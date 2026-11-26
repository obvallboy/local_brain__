// SB8 — a tiny but real 8-bit CPU core. Fetch/decode/execute, 8 registers,
// Z/C flags, program counter. This is the emulator engine; tested below.

function sb8Assemble(lines) {
  const instrs = [], labels = {}, errors = [];
  for (let raw of lines) {
    let line = String(raw).replace(/;.*/, "").trim();   // strip comments
    if (!line) continue;
    let m;
    while ((m = line.match(/^([A-Za-z_]\w*):\s*/))) {    // leading label(s)
      labels[m[1].toLowerCase()] = instrs.length;
      line = line.slice(m[0].length).trim();
      if (!line) break;
    }
    if (!line) continue;
    const sp = line.indexOf(" ");
    const mn = (sp < 0 ? line : line.slice(0, sp)).toUpperCase();
    const rest = sp < 0 ? "" : line.slice(sp + 1).trim();
    const ops = rest ? rest.split(",").map((x) => x.trim()).filter((x) => x.length) : [];
    instrs.push({ mn, ops, raw: line });
  }
  return { instrs, labels, errors };
}

function sb8ParseOp(tok) {
  tok = String(tok).trim().replace(/^\[|\]$/g, "");   // allow [Rs] memory syntax
  if (/^R[0-7]$/i.test(tok)) return { t: "reg", n: +tok.slice(1) };
  if (/^#?0x[0-9a-fA-F]+$/.test(tok)) return { t: "imm", v: parseInt(tok.replace("#", ""), 16) & 255 };
  if (/^#?-?\d+$/.test(tok)) return { t: "imm", v: (((parseInt(tok.replace("#", ""), 10)) % 256) + 256) % 256 };
  return { t: "label", name: tok.toLowerCase() };
}

function sb8Init() { return { regs: [0, 0, 0, 0, 0, 0, 0, 0], mem: {}, pc: 0, z: 0, c: 0, halted: false, out: [] }; }

function sb8Step(cpu, asm) {
  if (cpu.halted) return { done: true };
  if (cpu.pc < 0 || cpu.pc >= asm.instrs.length) { cpu.halted = true; return { done: true }; }
  const ins = asm.instrs[cpu.pc];
  const op = ins.ops.map(sb8ParseOp);
  const R = cpu.regs;
  const val = (o) => (o.t === "reg" ? R[o.n] : o.t === "imm" ? o.v : 0);
  const err = (msg) => { cpu.halted = true; return { error: msg + "  @ " + ins.raw }; };
  const needReg = (o) => o && o.t === "reg";
  const jumpTo = (o) => { const t = asm.labels[o.name]; if (t == null) return null; return t; };
  let next = cpu.pc + 1;
  switch (ins.mn) {
    case "MOV": if (!needReg(op[0])) return err("MOV needs a register destination"); R[op[0].n] = val(op[1]) & 255; break;
    case "ADD": { if (!needReg(op[0])) return err("ADD needs a register destination"); const a = R[op[0].n], b = val(op[1]), r = a + b; cpu.c = r > 255 ? 1 : 0; R[op[0].n] = r & 255; cpu.z = R[op[0].n] === 0 ? 1 : 0; break; }
    case "SUB": { if (!needReg(op[0])) return err("SUB needs a register destination"); const a = R[op[0].n], b = val(op[1]), r = a - b; cpu.c = a >= b ? 1 : 0; R[op[0].n] = ((r % 256) + 256) % 256; cpu.z = R[op[0].n] === 0 ? 1 : 0; break; }
    case "INC": { if (!needReg(op[0])) return err("INC needs a register"); R[op[0].n] = (R[op[0].n] + 1) & 255; cpu.z = R[op[0].n] === 0 ? 1 : 0; break; }
    case "DEC": { if (!needReg(op[0])) return err("DEC needs a register"); R[op[0].n] = ((R[op[0].n] - 1) % 256 + 256) % 256; cpu.z = R[op[0].n] === 0 ? 1 : 0; break; }
    case "CMP": { if (!needReg(op[0])) return err("CMP needs a register first"); const a = R[op[0].n], b = val(op[1]), r = ((a - b) % 256 + 256) % 256; cpu.c = a >= b ? 1 : 0; cpu.z = r === 0 ? 1 : 0; break; }
    case "LD": { if (!needReg(op[0]) || !needReg(op[1])) return err("LD Rd, [Rs]"); R[op[0].n] = (cpu.mem[R[op[1].n]] || 0) & 255; break; }
    case "ST": { if (!needReg(op[0]) || !needReg(op[1])) return err("ST [Rd], Rs"); cpu.mem[R[op[0].n]] = R[op[1].n] & 255; break; }
    case "JMP": { const t = jumpTo(op[0]); if (t == null) return err("unknown label"); next = t; break; }
    case "JZ": if (cpu.z) { const t = jumpTo(op[0]); if (t == null) return err("unknown label"); next = t; } break;
    case "JNZ": if (!cpu.z) { const t = jumpTo(op[0]); if (t == null) return err("unknown label"); next = t; } break;
    case "JC": if (cpu.c) { const t = jumpTo(op[0]); if (t == null) return err("unknown label"); next = t; } break;
    case "JNC": if (!cpu.c) { const t = jumpTo(op[0]); if (t == null) return err("unknown label"); next = t; } break;
    case "OUT": cpu.out.push(val(op[0]) & 255); break;
    case "NOP": break;
    case "HLT": cpu.halted = true; return { done: true };
    default: return err("unknown instruction '" + ins.mn + "'");
  }
  cpu.pc = next;
  return {};
}

function sb8Run(cpu, asm, cap) {
  cap = cap || 100000;
  let n = 0, error = null;
  while (!cpu.halted && n < cap) { const r = sb8Step(cpu, asm); if (r.error) { error = r.error; break; } n++; }
  return { steps: n, error: error, capped: n >= cap && !cpu.halted };
}

// ---------------- tests ----------------
const DEMOS = {
  sum: ["MOV R0,#0", "MOV R1,#1", "loop:", "ADD R0,R1", "INC R1", "MOV R3,#6", "CMP R1,R3", "JNZ loop", "OUT R0", "HLT"],
  fib: ["MOV R0,#0", "MOV R1,#1", "MOV R2,#10", "fibloop:", "OUT R0", "MOV R3,R0", "ADD R3,R1", "MOV R0,R1", "MOV R1,R3", "DEC R2", "JNZ fibloop", "HLT"],
  count: ["MOV R0,#1", "MOV R1,#10", "cloop:", "OUT R0", "INC R0", "CMP R0,R1", "JNZ cloop", "OUT R0", "HLT"],
};

function runDemo(name) { const asm = sb8Assemble(DEMOS[name]); const cpu = sb8Init(); const res = sb8Run(cpu, asm); return { out: cpu.out, regs: cpu.regs, res }; }

let ok = true;
function check(name, got, want) { const g = JSON.stringify(got), w = JSON.stringify(want); if (g !== w) { ok = false; console.log("FAIL", name, "got", g, "want", w); } else console.log("ok  ", name, g); }

check("sum=15", runDemo("sum").out, [15]);
check("fib10", runDemo("fib").out, [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]);
check("count1..10", runDemo("count").out, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);

// flags + step
{
  const asm = sb8Assemble(["MOV R0,#250", "ADD R0,#10", "HLT"]);
  const cpu = sb8Init();
  sb8Step(cpu, asm); sb8Step(cpu, asm);
  check("overflow wrap R0", [cpu.regs[0], cpu.c], [4, 1]); // 260 & 255 = 4, carry set
}
{
  const asm = sb8Assemble(["MOV R0,#5", "CMP R0,#5", "HLT"]);
  const cpu = sb8Init(); sb8Run(cpu, asm);
  check("cmp equal sets Z", [cpu.z, cpu.c], [1, 1]);
}
// memory + custom asm one-liner style
{
  const asm = sb8Assemble("MOV R0,#7; MOV R1,#20; ST [R1],R0; MOV R2,#20; LD R3,[R2]; OUT R3; HLT".split(";"));
  const cpu = sb8Init(); sb8Run(cpu, asm);
  check("mem store/load", cpu.out, [7]);
}
// infinite-loop cap
{
  const asm = sb8Assemble(["l:", "JMP l"]);
  const cpu = sb8Init(); const r = sb8Run(cpu, asm, 500);
  check("cap trips", [r.capped, r.steps], [true, 500]);
}

console.log(ok ? "\nALL PASS" : "\nFAILURES");
process.exit(ok ? 0 : 1);
