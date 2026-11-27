// Bluetooth (BLE): scan for nearby devices and connect, straight from the phone.
// Needs the Devy dev build (native code); in Expo Go it shows a notice.

import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { DEV_BUILD_NOTE, inExpoGo, loadBle } from './native';
import { C } from './theme';

type Dev = { id: string; name: string; rssi: number | null };

export default function Bluetooth() {
  const [scanning, setScanning] = useState(false);
  const [devices, setDevices] = useState<Record<string, Dev>>({});
  const [error, setError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [services, setServices] = useState<Record<string, string[]>>({});
  const managerRef = useRef<any>(null);

  useEffect(() => {
    return () => {
      try {
        managerRef.current?.destroy();
      } catch {
        // ignore
      }
    };
  }, []);

  if (inExpoGo) {
    return (
      <View style={styles.center}>
        <Text style={styles.notice}>{DEV_BUILD_NOTE}</Text>
      </View>
    );
  }

  const manager = () => {
    if (!managerRef.current) {
      const ble = loadBle();
      if (!ble) throw new Error('Bluetooth module not available.');
      managerRef.current = new ble.BleManager();
    }
    return managerRef.current;
  };

  const startScan = () => {
    setError(null);
    setDevices({});
    try {
      const m = manager();
      setScanning(true);
      m.startDeviceScan(null, null, (err: any, device: any) => {
        if (err) {
          setError(err.message || String(err));
          setScanning(false);
          return;
        }
        if (device) {
          setDevices((d) => ({
            ...d,
            [device.id]: { id: device.id, name: device.name || device.localName || '(no name)', rssi: device.rssi },
          }));
        }
      });
      setTimeout(() => stopScan(), 12000);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setScanning(false);
    }
  };

  const stopScan = () => {
    try {
      managerRef.current?.stopDeviceScan();
    } catch {
      // ignore
    }
    setScanning(false);
  };

  const connect = async (id: string) => {
    stopScan();
    setConnecting(id);
    setError(null);
    try {
      const dev = await manager().connectToDevice(id);
      await dev.discoverAllServicesAndCharacteristics();
      const svcs = await dev.services();
      setServices((s) => ({ ...s, [id]: svcs.map((sv: any) => sv.uuid) }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setConnecting(null);
    }
  };

  const list = Object.values(devices).sort((a, b) => (b.rssi ?? -999) - (a.rssi ?? -999));

  return (
    <ScrollView style={styles.flex} contentContainerStyle={styles.content}>
      <Text style={styles.hint}>
        Scan for Bluetooth devices nearby (an ESP32, a BLE sensor, headphones…). Tap one to connect and see its
        services. This runs on the phone — no server.
      </Text>
      <Pressable style={[styles.btn, styles.btnPrimary]} onPress={scanning ? stopScan : startScan}>
        {scanning ? (
          <View style={styles.row}>
            <ActivityIndicator color="#042" />
            <Text style={styles.btnPrimaryText}>  Scanning… (tap to stop)</Text>
          </View>
        ) : (
          <Text style={styles.btnPrimaryText}>Scan for devices</Text>
        )}
      </Pressable>
      {error && <Text style={styles.err}>{error}</Text>}

      {list.map((d) => (
        <Pressable key={d.id} style={styles.card} onPress={() => connect(d.id)} disabled={connecting === d.id}>
          <View style={styles.row}>
            <View style={styles.flex}>
              <Text style={styles.name}>{d.name}</Text>
              <Text style={styles.meta}>
                {d.id}
                {d.rssi != null ? ` · ${d.rssi} dBm` : ''}
              </Text>
            </View>
            {connecting === d.id ? <ActivityIndicator color={C.muted} /> : <Text style={styles.connect}>connect</Text>}
          </View>
          {services[d.id] && (
            <Text style={styles.svc}>Services: {services[d.id].join(', ') || 'none found'}</Text>
          )}
        </Pressable>
      ))}
      {scanning && list.length === 0 && <Text style={styles.empty}>Looking…</Text>}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  content: { padding: 12, gap: 8 },
  center: { flex: 1, padding: 24, justifyContent: 'center' },
  notice: { color: C.muted, fontSize: 14, lineHeight: 21, textAlign: 'center' },
  hint: { color: C.muted, fontSize: 13, lineHeight: 19 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  card: { backgroundColor: C.panel, borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 12 },
  name: { color: C.text, fontSize: 15, fontWeight: '600' },
  meta: { color: C.muted, fontSize: 12, marginTop: 2, fontFamily: 'monospace' },
  connect: { color: C.accent, fontSize: 13 },
  svc: { color: C.muted, fontSize: 12, marginTop: 8, fontFamily: 'monospace' },
  err: { color: C.err, fontSize: 13, padding: 4 },
  empty: { color: C.muted, fontSize: 14, textAlign: 'center', marginTop: 12 },
  btn: { borderRadius: 8, paddingHorizontal: 14, paddingVertical: 12, alignItems: 'center' },
  btnPrimary: { backgroundColor: C.accent },
  btnPrimaryText: { color: '#042', fontWeight: '700', fontSize: 15 },
});
