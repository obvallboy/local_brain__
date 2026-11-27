// What's plugged into the Devy computer, and a serial scanner for serial ports.
// All read from the server; the phone touches no hardware.

import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { DeviceSnapshot, getDevices, ScanResult, serialScan } from './api';
import { C } from './theme';

type Scan = { loading: boolean; result?: ScanResult; error?: string };

export default function Devices({ base }: { base: string }) {
  const [snap, setSnap] = useState<DeviceSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [scans, setScans] = useState<Record<string, Scan>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSnap(await getDevices(base));
    } catch (e) {
      setSnap(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [base]);

  useEffect(() => {
    load();
  }, [load]);

  const scan = async (port: string) => {
    setScans((s) => ({ ...s, [port]: { loading: true } }));
    try {
      const result = await serialScan(base, port);
      setScans((s) => ({ ...s, [port]: { loading: false, result } }));
    } catch (e) {
      setScans((s) => ({ ...s, [port]: { loading: false, error: e instanceof Error ? e.message : String(e) } }));
    }
  };

  const serial = snap?.serial ?? [];
  const usb = (snap?.usb ?? []).filter((d) => (d.device_class_name || '').toLowerCase() !== 'hub');
  const storage = snap?.storage ?? [];
  const network = (snap?.network ?? []).filter((n) => n.is_up !== false);

  return (
    <ScrollView
      style={styles.flex}
      contentContainerStyle={styles.content}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={C.muted} />}
    >
      {error && (
        <Text style={styles.err}>
          {error}
          {'\n\n'}Check the server address (⚙︎) and that your phone can reach it.
        </Text>
      )}
      {!error && !snap && <ActivityIndicator color={C.muted} style={{ marginTop: 24 }} />}

      {serial.length > 0 && <Text style={styles.section}>Serial ports</Text>}
      {serial.map((d, i) => {
        const port = d.device || '';
        const sc = scans[port];
        return (
          <View key={port || i} style={styles.card}>
            <View style={styles.row}>
              <View style={styles.flex}>
                <Text style={styles.name}>{d.device || 'serial port'}</Text>
                <Text style={styles.meta}>
                  {[d.description, d.vid ? `${d.vid}:${d.pid}` : null].filter(Boolean).join(' · ') || '—'}
                </Text>
              </View>
              <Pressable
                style={[styles.btn, sc?.loading && styles.btnDisabled]}
                onPress={() => scan(port)}
                disabled={sc?.loading || !port}
              >
                {sc?.loading ? <ActivityIndicator color={C.text} /> : <Text style={styles.btnText}>Scan</Text>}
              </Pressable>
            </View>
            {sc?.result && <Text style={styles.scan}>{sc.result.say}</Text>}
            {sc?.error && <Text style={[styles.scan, { color: C.err }]}>{sc.error}</Text>}
          </View>
        );
      })}

      {usb.length > 0 && <Text style={styles.section}>USB devices</Text>}
      {usb.map((d, i) => (
        <View key={i} style={styles.card}>
          <Text style={styles.name}>{d.product || d.manufacturer || `${d.vid}:${d.pid}`}</Text>
          <Text style={styles.meta}>
            {[d.device_class_name, d.vid ? `${d.vid}:${d.pid}` : null].filter(Boolean).join(' · ') || '—'}
          </Text>
        </View>
      ))}

      {network.length > 0 && <Text style={styles.section}>Network</Text>}
      {network.map((n, i) => (
        <View key={i} style={styles.card}>
          <Text style={styles.name}>{n.name}</Text>
          <Text style={styles.meta}>
            {(n.addresses ?? []).map((a) => a.address).filter(Boolean).slice(0, 2).join(' · ') || n.mac || '—'}
          </Text>
        </View>
      ))}

      {storage.length > 0 && <Text style={styles.section}>Storage</Text>}
      {storage.map((d, i) => (
        <View key={i} style={styles.card}>
          <Text style={styles.name}>{d.device}</Text>
          <Text style={styles.meta}>{[d.mountpoint, d.fstype].filter(Boolean).join(' · ') || '—'}</Text>
        </View>
      ))}

      {snap && serial.length + usb.length + network.length + storage.length === 0 && (
        <Text style={styles.empty}>Nothing attached that the server can see.</Text>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  content: { padding: 12, gap: 8 },
  section: { color: C.accent, fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.6, marginTop: 10, marginBottom: 2 },
  card: { backgroundColor: C.panel, borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 12 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  name: { color: C.text, fontSize: 15, fontWeight: '600' },
  meta: { color: C.muted, fontSize: 12, marginTop: 2, fontFamily: 'monospace' },
  scan: { color: C.text, fontSize: 13, lineHeight: 19, marginTop: 10, paddingTop: 10, borderTopWidth: 1, borderTopColor: C.border },
  btn: { borderWidth: 1, borderColor: C.border, borderRadius: 8, paddingHorizontal: 14, paddingVertical: 8, backgroundColor: C.panel2 },
  btnText: { color: C.text, fontSize: 13 },
  btnDisabled: { opacity: 0.6 },
  err: { color: C.err, fontSize: 14, lineHeight: 20, padding: 8 },
  empty: { color: C.muted, fontSize: 14, textAlign: 'center', marginTop: 24 },
});
