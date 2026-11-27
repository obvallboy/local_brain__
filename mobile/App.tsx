// Devy — a phone screen for the Device Integrator's local assistant.
// It runs no model and touches no hardware; it talks to the Devy server on your
// computer or Pi over your LAN or Tailscale. Set the server address with ⚙︎.

import AsyncStorage from '@react-native-async-storage/async-storage';
import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useState } from 'react';
import { Platform, Pressable, SafeAreaView, StyleSheet, Text, TextInput, View } from 'react-native';
import { getStatus, normalizeBase, Status } from './src/api';
import Chat from './src/Chat';
import Devices from './src/Devices';
import Bluetooth from './src/Bluetooth';
import Reference from './src/Reference';
import { C } from './src/theme';

const URL_KEY = 'devy.serverUrl';
const DEFAULT_URL = 'http://192.168.1.100:5000';
type Tab = 'chat' | 'devices' | 'bluetooth' | 'reference';

export default function App() {
  const [serverUrl, setServerUrl] = useState(DEFAULT_URL);
  const [draftUrl, setDraftUrl] = useState(DEFAULT_URL);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);
  const [statusErr, setStatusErr] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('chat');

  const base = normalizeBase(serverUrl);

  const refreshStatus = useCallback(async (b: string) => {
    setStatusErr(null);
    try {
      setStatus(await getStatus(b));
    } catch (e) {
      setStatus(null);
      setStatusErr(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    (async () => {
      let saved = DEFAULT_URL;
      try {
        saved = (await AsyncStorage.getItem(URL_KEY)) || DEFAULT_URL;
      } catch {
        // storage can be unavailable; fall back to the default
      }
      setServerUrl(saved);
      setDraftUrl(saved);
      refreshStatus(normalizeBase(saved));
    })();
  }, [refreshStatus]);

  const saveUrl = async () => {
    const clean = normalizeBase(draftUrl);
    setServerUrl(clean);
    setSettingsOpen(false);
    try {
      await AsyncStorage.setItem(URL_KEY, clean);
    } catch {
      // best effort
    }
    refreshStatus(clean);
  };

  const statusLine = statusErr
    ? `not connected — ${statusErr}`
    : !status
    ? 'connecting…'
    : !status.ready
    ? status.loading
      ? 'loading the model…'
      : 'starting…'
    : status.model
    ? `model: ${status.model}${status.embed ? ' · meaning-matching on' : ''}${status.gpu_layers ? ' · GPU' : ''}`
    : 'drawers & rules only (no model)';

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="light" />
      <View style={styles.header}>
        <View style={styles.flex}>
          <Text style={styles.title}>🧠 Devy</Text>
          <Text style={styles.status} numberOfLines={1}>
            {statusLine}
          </Text>
        </View>
        <Pressable
          onPress={() => {
            setDraftUrl(serverUrl);
            setSettingsOpen((s) => !s);
          }}
          hitSlop={10}
        >
          <Text style={styles.gear}>⚙︎</Text>
        </Pressable>
      </View>

      {settingsOpen && (
        <View style={styles.settings}>
          <Text style={styles.settingsLabel}>Devy server address</Text>
          <TextInput
            style={styles.urlInput}
            value={draftUrl}
            onChangeText={setDraftUrl}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            placeholder="http://100.x.y.z:5000"
            placeholderTextColor={C.muted}
          />
          <Text style={styles.hint}>
            Your computer's Tailscale or LAN address and the port (default 5000). Run the app there with{' '}
            <Text style={styles.code}>python app.py --host 0.0.0.0</Text>.
          </Text>
          <View style={styles.settingsRow}>
            <Pressable style={[styles.btn, styles.btnPrimary]} onPress={saveUrl}>
              <Text style={styles.btnPrimaryText}>Save & connect</Text>
            </Pressable>
            <Pressable style={styles.btn} onPress={() => refreshStatus(base)}>
              <Text style={styles.btnText}>Test</Text>
            </Pressable>
          </View>
        </View>
      )}

      <View style={styles.tabs}>
        {(['chat', 'devices', 'bluetooth', 'reference'] as Tab[]).map((t) => (
          <Pressable key={t} style={[styles.tab, tab === t && styles.tabActive]} onPress={() => setTab(t)}>
            <Text style={[styles.tabText, tab === t && styles.tabTextActive]}>
              {t === 'chat' ? 'Chat' : t === 'devices' ? 'Devices' : t === 'bluetooth' ? 'Bluetooth' : 'Reference'}
            </Text>
          </Pressable>
        ))}
      </View>

      {tab === 'chat' ? (
        <Chat base={base} />
      ) : tab === 'devices' ? (
        <Devices base={base} />
      ) : tab === 'bluetooth' ? (
        <Bluetooth />
      ) : (
        <Reference />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  flex: { flex: 1 },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: C.border,
    backgroundColor: C.panel,
  },
  title: { color: C.text, fontSize: 18, fontWeight: '700' },
  status: { color: C.muted, fontSize: 12, marginTop: 2 },
  gear: { color: C.text, fontSize: 22, padding: 4 },
  settings: { padding: 16, backgroundColor: C.panel2, borderBottomWidth: 1, borderBottomColor: C.border },
  settingsLabel: { color: C.muted, fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 6 },
  urlInput: {
    backgroundColor: C.bg,
    color: C.text,
    borderWidth: 1,
    borderColor: C.border,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 10,
    fontSize: 15,
  },
  hint: { color: C.muted, fontSize: 12, marginTop: 8, lineHeight: 17 },
  code: { fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', color: C.text },
  settingsRow: { flexDirection: 'row', gap: 8, marginTop: 12 },
  tabs: { flexDirection: 'row', backgroundColor: C.panel, borderBottomWidth: 1, borderBottomColor: C.border },
  tab: { flex: 1, paddingVertical: 11, alignItems: 'center', borderBottomWidth: 2, borderBottomColor: 'transparent' },
  tabActive: { borderBottomColor: C.accent },
  tabText: { color: C.muted, fontSize: 13, fontWeight: '600' },
  tabTextActive: { color: C.text },
  btn: { borderWidth: 1, borderColor: C.border, borderRadius: 8, paddingHorizontal: 14, paddingVertical: 10, backgroundColor: C.panel2 },
  btnText: { color: C.text, fontSize: 14 },
  btnPrimary: { backgroundColor: C.accent, borderColor: 'transparent' },
  btnPrimaryText: { color: '#042', fontWeight: '700', fontSize: 14 },
});
