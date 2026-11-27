// Native features (Bluetooth, on-phone model) need real native code, which Expo Go
// can't load. This detects Expo Go and lazily loads the native modules only when we're
// in a dev build — so the app still runs in Expo Go, with those features showing a notice.

import Constants, { ExecutionEnvironment } from 'expo-constants';

// Expo Go runs as the "store client"; a dev/standalone build does not.
export const inExpoGo = Constants.executionEnvironment === ExecutionEnvironment.StoreClient;

// Lazy, guarded loaders. Return null in Expo Go (or if the module can't load).
export function loadBle(): any | null {
  if (inExpoGo) return null;
  try {
    return require('react-native-ble-plx');
  } catch {
    return null;
  }
}

export function loadLlama(): any | null {
  if (inExpoGo) return null;
  try {
    return require('llama.rn');
  } catch {
    return null;
  }
}

export const DEV_BUILD_NOTE =
  'This needs the Devy dev build (native code) — it can’t run in Expo Go. See mobile/DEV_BUILD.md to build it ' +
  'once with EAS (no Mac needed). Everything else in the app still works here.';
