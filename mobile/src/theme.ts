// Devy's colors, matching the Device Integrator's web panel, and the label colors.

export const C = {
  bg: '#0e1116',
  panel: '#161b22',
  panel2: '#1c232d',
  border: '#2a333f',
  text: '#e6edf3',
  muted: '#8b98a5',
  accent: '#39d0d8',
  accent2: '#f0883e',
  ok: '#3fb950',
  err: '#f85149',
  remember: '#b392f0',
  core: '#f778ba',
};

// The honesty label on every answer gets a color, same meaning as on the web.
export function labelColor(label: string): string {
  switch (label) {
    case 'I know':
    case 'Filed':
      return C.ok;
    case 'I think':
      return C.accent2;
    case 'I checked':
      return C.accent;
    case 'I remember':
      return C.remember;
    case 'From my core':
      return C.core;
    case 'Removed':
      return C.err;
    default:
      return C.muted; // I'm not sure, I don't remember, Command
  }
}
