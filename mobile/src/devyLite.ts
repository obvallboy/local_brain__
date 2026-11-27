// Devy Lite — a rules-only Devy that runs entirely on the phone, no server, no model.
// It can learn/recall facts, forget, give opinions, recognize boards, and keep people safe.
// It honestly can't answer general-knowledge questions (that needs the big model on a server).
// A focused TypeScript port of the File Cabinet's rules; memory lives in AsyncStorage.

import AsyncStorage from '@react-native-async-storage/async-storage';
import { identify, search, summaryLine } from './boards';

export type LiteLabel = 'I know' | 'Filed' | 'Removed' | "I'm not sure" | 'From my core';
export type LiteAnswer = { label: LiteLabel; text: string };

export type Fact = { id: number; subject: string; fact: string };
export type Pref = { item: string; stance: 'like' | 'dislike'; reason: string };
export type Memory = { facts: Fact[]; prefs: Pref[]; nextId: number };

const KEY = 'devy.lite.memory';
export const emptyMemory = (): Memory => ({ facts: [], prefs: [], nextId: 1 });

export async function loadMemory(): Promise<Memory> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (raw) return { ...emptyMemory(), ...JSON.parse(raw) };
  } catch {
    // storage unavailable; start empty
  }
  return emptyMemory();
}

export async function saveMemory(m: Memory): Promise<void> {
  try {
    await AsyncStorage.setItem(KEY, JSON.stringify(m));
  } catch {
    // best effort
  }
}

// ---- small text helpers --------------------------------------------------------
const STOP = new Set(
  ("a an the is are was were be been am i im you we he she it they me my your our his her its their this that these " +
    "those of in on at to for from with by about as and or but if then so do does did have has had what which who " +
    "whom when where why how can could would should will may might must not no yes there here just also very really " +
    "any some all each every than too into out up down over under again once us them him what's who's where's how's")
    .split(/\s+/)
);
function tokens(s: string): string[] {
  return (s.toLowerCase().replace(/[’]/g, "'").match(/[a-z0-9']+/g) || [])
    .map((w) => w.replace(/'s$/, '').replace(/^'|'$/g, ''))
    .filter((w) => w && !STOP.has(w));
}
const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);

// ---- regexes (ported, simplified) ----------------------------------------------
const CRISIS = /\b(suicid\w*|kill(ing)? myself|end(ing)? my life|end(ing)? it all|hurt(ing)? myself|harm(ing)? myself|self[- ]harm|want to die|wanna die|no reason to live|better off without me|(don't|do not|dont) want to (be here|live|wake up)|can't (keep going|go on)|(don't|do not|dont) (know|see) (if|how|the point))\b/i;
const DEEP = /\b(died|death|passed away|funeral|grie(f|ving|ve)|divorc\w*|broke up|break ?up|fought|betray\w*|depress\w*|lonely|hopeless|worthless|pointless|heartbroken|bad news|nobody (gets|cares)|(feel|feeling|been) (really |so |kinda |pretty )?(down|sad|awful)|lost (my|a|our) (friend|mom|dad|brother|sister|dog|cat|pet|job))\b/i;
const FILLER = /^(fyi|btw|by the way|just so you know|for the record|note that|remember that|remember:|keep in mind that|keep in mind|don't forget that|don't forget|dont forget|heads up)[,:]?\s+/i;
const FORGET = /^(please |can you |could you )?(forget|delete|remove|erase|unlearn)\b/i;
const QUESTION = /\?\s*$|^\s*(what|what's|who|who's|when|where|where's|why|how|how's|which|is|are|was|were|do|does|did|can|could|will|would|should|remind me|tell me)\b/i;
const OPINION = /\b(funny|pretty|cute|cool|ugly|nice|beautiful|awesome|boring|do you like|you like|do you love|favou?rite|prefer)\b/i;
const PROGRAM = /\b(how (do|can|would) i|how to)\b.*\b(program|flash|upload|code|use)\b|\bwhat (is|'s)\b.*\b(board|chip|pico|esp32|esp8266|arduino|micro:?bit|stm32|teensy)\b|\bhow do i program\b/i;
const CRISIS_LINE =
  ' If you might hurt yourself, please reach out right now to someone you trust or a crisis line. In the US you can call or text 988.';

// ---- fact extraction (port of teach.py subset) ---------------------------------
function secondPerson(t: string): string {
  let s = t
    .replace(/\bi was\b/g, 'you were')
    .replace(/\bi am\b/g, 'you are')
    .replace(/\bi'm\b/g, "you're")
    .replace(/\bi've\b/g, "you've");
  const map: Record<string, string> = { my: 'your', mine: 'yours', i: 'you', me: 'you', myself: 'yourself' };
  s = s.replace(/\b(my|mine|i|me|myself)\b/g, (w) => map[w]);
  return cap(s) + '.';
}

function extractFact(raw: string): { subject: string; fact: string } | null {
  let t = raw.trim().toLowerCase().replace(/[’]/g, "'").replace(/[.!]+$/, '');
  t = t.replace(FILLER, '');
  let m: RegExpMatchArray | null;
  if ((m = t.match(/^my ([\w' ]+?)(?:'s)? name is (.+)$/))) return { subject: m[1], fact: `Your ${m[1]}'s name is ${m[2]}.` };
  if ((m = t.match(/^my ([\w' ]+?) is (?:named|called) (.+)$/))) return { subject: m[1], fact: `Your ${m[1]} is named ${m[2]}.` };
  if ((m = t.match(/^(?!(?:this|that|it|he|she|they|there|here|what|who)\b)([\w']+) is my ((?:[\w']+ ){0,2}[\w']+)$/)))
    return { subject: `${m[2]} ${m[1]}`, fact: `${cap(m[1])} is your ${m[2]}.` };
  if ((m = t.match(/^my ((?:[\w']+ ){0,2}[\w']+) (is|are|was|were|lives|works|has|likes|loves|hates|plays|drives|goes|studies)\b/)))
    return { subject: m[1], fact: secondPerson(t) };
  if ((m = t.match(/^(?:i'm|i am) (allergic to|from) (.+)$/))) return { subject: m[1].split(' ')[0], fact: secondPerson(t) };
  if ((m = t.match(/^(?:i'm|i am) (\d+)(?: years old)?$/))) return { subject: 'age, how old', fact: `You are ${m[1]} years old.` };
  if ((m = t.match(/^i (drive|own|play|speak|ride)\b/))) return { subject: m[1], fact: secondPerson(t) };
  if ((m = t.match(/^i (work|live|was born|grew up|study|go to|am from|'m from)\b/))) return { subject: m[1], fact: secondPerson(t) };
  return null;
}

function findFact(query: string, facts: Fact[]): Fact | null {
  const q = new Set(tokens(query));
  let best: Fact | null = null;
  let bestScore = 0;
  for (const f of facts) {
    if (!tokens(f.subject).some((t) => q.has(t))) continue;
    const overlap = tokens(`${f.subject} ${f.fact}`).filter((t) => q.has(t)).length;
    if (overlap >= 1 && overlap >= bestScore) {
      bestScore = overlap;
      best = f; // ties favor the newest fact (later in the list)
    }
  }
  return best;
}

// ---- the engine ----------------------------------------------------------------
export function respond(raw: string, mem: Memory): { answer: LiteAnswer; mem: Memory } {
  const text = raw.trim();
  const low = text.toLowerCase();
  const isQ = QUESTION.test(text);
  const crisis = CRISIS.test(low);

  // 1. Safety first.
  if (crisis || (DEEP.test(low) && !isLikeLookup(low, mem))) {
    const words = crisis
      ? "I'm really sorry you're feeling that way. You're not alone, and talking to someone can help." + CRISIS_LINE
      : "That sounds really hard. I'm here, and I'm listening. Do you want to tell me what happened?";
    return { answer: { label: 'From my core', text: words }, mem };
  }

  // 2. Forget.
  if (!isQ && FORGET.test(low)) {
    const what = low.replace(FORGET, '').replace(/^\s*(that|about|the fact that)\s+/, '').trim();
    const hit = what ? findFact(what, mem.facts) : null;
    if (!hit) return { answer: { label: "I'm not sure", text: "I don't have that on the phone, so there's nothing to forget." }, mem };
    const facts = mem.facts.filter((f) => f.id !== hit.id && f.subject !== hit.subject);
    return { answer: { label: 'Removed', text: `Removed from memory: ${hit.fact}` }, mem: { ...mem, facts } };
  }

  // 3. Learn a fact from a statement.
  if (!isQ) {
    const taught = extractFact(text);
    if (taught) {
      const fact: Fact = { id: mem.nextId, subject: taught.subject, fact: taught.fact };
      return { answer: { label: 'Filed', text: `Got it. Saved on your phone: ${taught.fact}` }, mem: { ...mem, facts: [...mem.facts, fact], nextId: mem.nextId + 1 } };
    }
    // like/dislike
    let m: RegExpMatchArray | null;
    if ((m = low.match(/^i (really )?(like|love|enjoy|prefer|hate|dislike) (.+)$/))) {
      const stance = /hate|dislike/.test(m[2]) ? 'dislike' : 'like';
      const item = m[3].replace(/[.!]+$/, '').trim();
      const prefs = [...mem.prefs.filter((p) => p.item !== item), { item, stance: stance as 'like' | 'dislike', reason: '' }];
      return { answer: { label: 'Filed', text: `Got it: you ${stance} ${item}.` }, mem: { ...mem, prefs } };
    }
  }

  // 4. Board / "how do I program" questions — answered from the offline registry.
  if (PROGRAM.test(low) || /\b(pico|rp2040|esp32|esp8266|arduino|micro:?bit|stm32|teensy|nodemcu)\b/i.test(low)) {
    const vidpid = low.match(/\b([0-9a-f]{4})[: ]([0-9a-f]{4})\b/);
    const hit = vidpid ? identify(vidpid[1], vidpid[2]) : search(stripProgramWords(low))[0];
    if (hit) return { answer: { label: 'I know', text: summaryLine(hit) }, mem };
  }

  // 5. A fact question — look in phone memory.
  if (isQ || /\bmy\b/.test(low)) {
    const hit = findFact(text, mem.facts);
    if (hit) return { answer: { label: 'I know', text: hit.fact }, mem };
    // an opinion we were taught
    const pref = isLikeLookup(low, mem);
    if (pref) {
      const words = pref.stance === 'like' ? `Yes, you like ${pref.item}.` : `No, you don't like ${pref.item}.`;
      return { answer: { label: 'I know', text: words }, mem };
    }
  }

  // 6. Opinion with nothing filed.
  if (OPINION.test(low)) {
    return { answer: { label: "I'm not sure", text: "I don't have an opinion on that saved yet. Tell me \"I like …\" and I'll remember." }, mem };
  }

  // 7. Greetings / thanks.
  if (/^(hi|hey|hello|yo|sup|good (morning|evening|afternoon)|thanks|thank you|ty)\b/.test(low)) {
    return { answer: { label: 'I know', text: "Hey — I'm running right here on your phone. Ask me about a board, or tell me something to remember." }, mem };
  }

  // 8. Honest fallback: no model on the phone.
  return {
    answer: {
      label: "I'm not sure",
      text:
        "I can't answer that just on your phone — I don't have the big model here. I can look up boards, and " +
        "remember things you tell me. For general questions, connect to a Devy server (the Chat tab, Server mode).",
    },
    mem,
  };
}

function isLikeLookup(low: string, mem: Memory): Pref | null {
  for (const p of mem.prefs) if (low.includes(p.item)) return p;
  return null;
}

function stripProgramWords(low: string): string {
  return low
    .replace(/\b(how|do|can|would|i|to|program|flash|upload|code|use|what|is|the|a|an|my|'s)\b/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}
