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

export type SerialPort = { device?: string; description?: string; vid?: string; pid?: string; key?: string };
export type UsbDevice = { product?: string; manufacturer?: string; vid?: string; pid?: string; device_class_name?: string };
export type StorageDevice = { device?: string; mountpoint?: string; fstype?: string };
export type NetIface = { name?: string; is_up?: boolean; addresses?: { address?: string }[]; mac?: string };
export type DeviceSnapshot = {
  capabilities?: { platform?: string };
  serial: SerialPort[];
  usb: UsbDevice[];
  storage: StorageDevice[];
  network: NetIface[];
};

export type ScanResult = {
  baud: number | null;
  what: string | null;
  next_step: string | null;
  sample: string;
  say: string;
};

export function getDevices(base: string): Promise<DeviceSnapshot> {
  return req<DeviceSnapshot>(base, '/api/devices', undefined, 10000);
}

export function serialScan(base: string, port: string): Promise<ScanResult> {
  return req<ScanResult>(base, `/api/brain/serial-scan?port=${encodeURIComponent(port)}`, undefined, 20000);
}

export type NetScanResult = {
  host: string;
  open_ports: number[];
  guess: string | null;
  steps: string[];
  say: string;
};

export function netScan(base: string, host: string): Promise<NetScanResult> {
  return req<NetScanResult>(base, `/api/brain/net-scan?host=${encodeURIComponent(host)}`, undefined, 25000);
}

export type PhoneProbe = { reachable: boolean; info: string };

// Reach a device over Wi-Fi straight from the phone (no server). HTTP only — the phone
// can't do a raw port scan, but it can open a device's web server.
export async function phoneHttpProbe(host: string): Promise<PhoneProbe> {
  const h = host.trim().replace(/^https?:\/\//i, '').replace(/\/+$/, '');
  for (const url of [`http://${h}`, `http://${h}:8080`]) {
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 5000);
      const res = await fetch(url, { method: 'GET', signal: ctrl.signal });
      clearTimeout(timer);
      const server = res.headers.get('server');
      return {
        reachable: true,
        info: `${url} answered (HTTP ${res.status}${server ? `, Server: ${server}` : ''}). Open it in a browser.`,
      };
    } catch {
      // try the next url
    }
  }
  return {
    reachable: false,
    info: `Couldn't reach ${h} over HTTP from this phone. It may use HTTPS, a different port, or have no web server. A full port scan (SSH, MQTT, ESP OTA…) needs the Devy server's net-scan above.`,
  };
}
