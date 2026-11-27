// Offline board/chip knowledge — a TypeScript port of the File Cabinet's boards.py,
// using the same data/usb_ids.json. Works on the phone with no server.

import db from './data/usb_ids.json';

export type BoardInfo = {
  name: string;
  kind: string; // board | bridge | bootloader | tool
  confidence: 'exact' | 'vendor' | 'hint';
  chip?: string;
  voltage?: string;
  baud?: string;
  tools: string[];
  languages: string[];
  note?: string;
};

type Entry = {
  name: string;
  kind?: string;
  chip?: string;
  voltage?: string;
  baud?: string;
  tools?: string[];
  languages?: string[];
  note?: string;
};

const EXACT = db.exact as Record<string, Entry>;
const VENDOR = db.vendor as Record<string, Entry>;
const HINTS = db.hints as [string, Entry][];

function make(entry: Entry, confidence: BoardInfo['confidence']): BoardInfo {
  return {
    name: entry.name,
    kind: entry.kind || 'board',
    confidence,
    chip: entry.chip,
    voltage: entry.voltage,
    baud: entry.baud,
    tools: entry.tools || [],
    languages: entry.languages || [],
    note: entry.note,
  };
}

const norm = (v?: string) => (v || '').trim().toLowerCase().replace(/^0x/, '');

export function identify(vid?: string, pid?: string, product?: string): BoardInfo | null {
  const v = norm(vid);
  const p = norm(pid);
  if (v && p && EXACT[`${v}:${p}`]) return make(EXACT[`${v}:${p}`], 'exact');
  if (v && VENDOR[v]) return make(VENDOR[v], 'vendor');
  if (product) {
    const low = product.toLowerCase();
    for (const [needle, entry] of HINTS) {
      if (low.includes(needle)) return make(entry, 'hint');
    }
  }
  return null;
}

export function isBridge(b: BoardInfo): boolean {
  return b.kind === 'bridge';
}

function joinOr(items: string[]): string {
  if (items.length === 1) return items[0];
  if (items.length === 2) return `${items[0]} or ${items[1]}`;
  return items.slice(0, -1).join(', ') + `, or ${items[items.length - 1]}`;
}

export function summaryLine(b: BoardInfo): string {
  let head = b.name;
  const spec = [b.chip, b.voltage].filter(Boolean).join(', ');
  if (spec) head += ` (${spec})`;
  if (isBridge(b)) return head + ' — a USB-to-serial bridge chip, not a board on its own';
  let tail = '';
  if (b.languages.length) {
    tail = ` — program with ${joinOr(b.languages)}`;
    if (b.tools.length) tail += ` using ${joinOr(b.tools)}`;
  }
  if (b.baud) tail += `; serial ${b.baud} baud`;
  return head + tail;
}

// A flat, de-duplicated list for searching by name/chip.
const ALL: BoardInfo[] = (() => {
  const seen = new Set<string>();
  const out: BoardInfo[] = [];
  const add = (b: BoardInfo) => {
    if (!seen.has(b.name)) {
      seen.add(b.name);
      out.push(b);
    }
  };
  Object.values(EXACT).forEach((e) => add(make(e, 'exact')));
  Object.values(VENDOR).forEach((e) => add(make(e, 'vendor')));
  HINTS.forEach(([, e]) => add(make(e, 'hint')));
  return out;
})();

const VIDPID = /^([0-9a-f]{4})[: ]([0-9a-f]{4})$/i;

// Search by a board name, chip, language, or a "vid:pid" id. Returns best matches first.
export function search(query: string): BoardInfo[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const m = q.match(VIDPID);
  if (m) {
    const hit = identify(m[1], m[2]);
    return hit ? [hit] : [];
  }
  const terms = q.split(/\s+/);
  const scored = ALL.map((b) => {
    const hay = [b.name, b.chip, ...b.languages, ...b.tools].filter(Boolean).join(' ').toLowerCase();
    const score = terms.reduce((s, t) => s + (hay.includes(t) ? 1 : 0), 0);
    return { b, score };
  }).filter((x) => x.score > 0);
  scored.sort((a, b) => b.score - a.score);
  return scored.map((x) => x.b);
}
