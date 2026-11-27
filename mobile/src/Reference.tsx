// Offline hardware reference — works on the phone alone, no server.
// Look up a board/chip and how to program it, plus a small cheat-sheet.

import { useMemo, useState } from 'react';
import { ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { search, summaryLine } from './boards';
import { C } from './theme';

const SERIAL_SIGNS: [string, string][] = [
  ['>>>', 'MicroPython / CircuitPython REPL — type Python at it'],
  ['=> or "U-Boot"', 'U-Boot bootloader — press a key to stop autoboot, then "help"'],
  ['login:', 'a Linux login — needs a username/password'],
  ['rst:0x / ets ...', 'an ESP32/ESP8266 boot log (boot ROM often 74880 baud)'],
  ['$GPGGA,...', 'a GPS streaming NMEA (usually 9600 baud)'],
  ['OK (to "AT")', 'an AT-command modem'],
];

const PORTS: [string, string][] = [
  ['22', 'SSH — ssh user@host'],
  ['80 / 443', 'web UI — open in a browser'],
  ['23', 'Telnet console (unencrypted; routers/embedded)'],
  ['1883', 'MQTT (IoT messaging)'],
  ['3232', 'Arduino/ESP OTA — flash over Wi-Fi'],
  ['554', 'RTSP camera stream'],
  ['9100', 'network printer'],
  ['5555', 'Android ADB'],
];

export default function Reference() {
  const [q, setQ] = useState('');
  const results = useMemo(() => search(q).slice(0, 12), [q]);

  return (
    <ScrollView style={styles.flex} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
      <Text style={styles.offline}>Works offline — no server needed.</Text>

      <TextInput
        style={styles.input}
        value={q}
        onChangeText={setQ}
        autoCapitalize="none"
        autoCorrect={false}
        placeholder="a board, chip, or vid:pid — e.g. pico, esp32, 2e8a:0005"
        placeholderTextColor={C.muted}
      />

      {q.trim().length > 0 && results.length === 0 && (
        <Text style={styles.empty}>No match. Try a board name (pico, esp32, arduino), a chip, or a USB id.</Text>
      )}
      {results.map((b, i) => (
        <View key={i} style={styles.card}>
          <Text style={styles.name}>{b.name}</Text>
          <Text style={styles.summary}>{summaryLine(b)}</Text>
          {b.note && <Text style={styles.note}>{b.note}</Text>}
        </View>
      ))}

      {q.trim().length === 0 && (
        <>
          <Text style={styles.section}>What's answering on serial?</Text>
          {SERIAL_SIGNS.map(([sign, meaning]) => (
            <View key={sign} style={styles.cheat}>
              <Text style={styles.cheatKey}>{sign}</Text>
              <Text style={styles.cheatVal}>{meaning}</Text>
            </View>
          ))}
          <Text style={styles.section}>Common network ports</Text>
          {PORTS.map(([port, meaning]) => (
            <View key={port} style={styles.cheat}>
              <Text style={styles.cheatKey}>{port}</Text>
              <Text style={styles.cheatVal}>{meaning}</Text>
            </View>
          ))}
          <Text style={styles.foot}>
            Most dev boards are 3.3 V; the Arduino Uno is 5 V. Never wire a 5 V or RS-232 line to a 3.3 V board or
            a Pi.
          </Text>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  content: { padding: 12, gap: 8 },
  offline: { color: C.ok, fontSize: 12, textAlign: 'center' },
  input: {
    backgroundColor: C.bg,
    color: C.text,
    borderWidth: 1,
    borderColor: C.border,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
  },
  empty: { color: C.muted, fontSize: 14, padding: 8 },
  card: { backgroundColor: C.panel, borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 12 },
  name: { color: C.text, fontSize: 15, fontWeight: '700' },
  summary: { color: C.text, fontSize: 14, lineHeight: 20, marginTop: 4 },
  note: { color: C.muted, fontSize: 12, lineHeight: 18, marginTop: 6 },
  section: { color: C.accent, fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.6, marginTop: 14, marginBottom: 2 },
  cheat: { flexDirection: 'row', gap: 10, paddingVertical: 4 },
  cheatKey: { color: C.accent2, fontFamily: 'monospace', fontSize: 13, width: 112 },
  cheatVal: { color: C.text, fontSize: 13, flex: 1, lineHeight: 18 },
  foot: { color: C.muted, fontSize: 12, lineHeight: 18, marginTop: 14 },
});
