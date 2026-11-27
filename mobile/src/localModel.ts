// A real on-phone model (llama.cpp via llama.rn). Runs a small GGUF model on the
// device — no server. Only works in the Devy dev build (native code); in Expo Go it's
// unavailable and the on-phone chat stays rules-only.
//
// EXPERIMENTAL and untested on a physical device from this repo. The model is ~0.5B
// (about 400 MB) so it fits an iPhone; expect modest quality and a one-time download.

import * as FileSystem from 'expo-file-system/legacy';
import { inExpoGo, loadLlama } from './native';

const MODEL_URL =
  'https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf';
const MODEL_PATH = (FileSystem.documentDirectory || '') + 'qwen2.5-0.5b-instruct-q4_k_m.gguf';

let ctx: any = null;

export function modelSupported(): boolean {
  return !inExpoGo && loadLlama() != null;
}

export async function modelDownloaded(): Promise<boolean> {
  try {
    const info = await FileSystem.getInfoAsync(MODEL_PATH);
    return info.exists && (info.size ?? 0) > 1_000_000;
  } catch {
    return false;
  }
}

export async function downloadModel(onProgress?: (fraction: number) => void): Promise<void> {
  const task = FileSystem.createDownloadResumable(MODEL_URL, MODEL_PATH, {}, (p) => {
    const total = p.totalBytesExpectedToWrite || 1;
    onProgress?.(p.totalBytesWritten / total);
  });
  await task.downloadAsync();
}

export async function loadModel(): Promise<void> {
  if (ctx) return;
  const llama = loadLlama();
  if (!llama) throw new Error('The on-phone model needs the Devy dev build.');
  if (!(await modelDownloaded())) throw new Error('Model not downloaded yet.');
  ctx = await llama.initLlama({ model: MODEL_PATH, n_ctx: 2048, n_gpu_layers: 99 });
}

export function modelReady(): boolean {
  return ctx != null;
}

// Answer a general question with the on-phone model. Kept short and deterministic.
export async function askModel(question: string): Promise<string> {
  if (!ctx) await loadModel();
  const res = await ctx.completion({
    messages: [
      { role: 'system', content: 'Answer in one short, factual sentence. If you are unsure, say so.' },
      { role: 'user', content: question },
    ],
    n_predict: 120,
    temperature: 0,
  });
  return String(res?.text ?? '').trim();
}

export async function unloadModel(): Promise<void> {
  if (ctx) {
    try {
      await ctx.release();
    } catch {
      // ignore
    }
    ctx = null;
  }
}
