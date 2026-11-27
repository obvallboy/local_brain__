// Talks to a Devy server (the Device Integrator) over the network — your LAN or Tailscale.
// Nothing runs on the phone; the model and the hardware stay on your computer.

export type Status = {
  ready: boolean;
  loading?: boolean;
  model?: string | null;
  embed?: string | null;
  confidence_cutoff?: number | null;
  gpu_layers?: number;
  memory_file?: string;
  notes?: string[];
};

export type AskResult = {
  label: string;
  text: string;
  route?: { kind: string; depth: string; reason: string };
  drawers?: string[];
  evidence?: string[];
};

export function normalizeBase(raw: string): string {
  let url = (raw || '').trim();
  if (!url) return '';
  if (!/^https?:\/\//i.test(url)) url = 'http://' + url;
  return url.replace(/\/+$/, '');
}

async function req<T>(base: string, path: string, init?: RequestInit, timeoutMs = 20000): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(base + path, { ...init, signal: controller.signal });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error((data && (data as { error?: string }).error) || `HTTP ${res.status}`);
    }
    return data as T;
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new Error('timed out — is the server running and reachable at this address?');
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export function getStatus(base: string): Promise<Status> {
  return req<Status>(base, '/api/brain/status', undefined, 8000);
}

export function ask(base: string, message: string): Promise<AskResult> {
  return req<AskResult>(base, '/api/brain/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  });
}
