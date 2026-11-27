// Chat with Devy. Two modes: Server (talks to the Devy server) and On-phone
// (Devy Lite — runs entirely on the phone, no server, no big model).

import { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { ask, AskResult } from './api';
import { loadMemory, Memory, respond, saveMemory } from './devyLite';
import { C, labelColor } from './theme';

const QUICK_SERVER = ["What's plugged in?", 'How do I program my Pico?', '/help'];
const QUICK_LOCAL = ['How do I program an ESP32?', 'What is a Raspberry Pi Pico?', 'my name is …'];

type Mode = 'server' | 'local';
type Msg = { id: string; role: 'me' | 'devy' | 'error'; text: string; result?: AskResult };
let counter = 0;
const nextId = () => `${Date.now()}-${counter++}`;

export default function Chat({ base }: { base: string }) {
  const [mode, setMode] = useState<Mode>('server');
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const memRef = useRef<Memory | null>(null);
  const listRef = useRef<FlatList<Msg>>(null);

  useEffect(() => {
    loadMemory().then((m) => {
      memRef.current = m;
    });
  }, []);

  const send = async (text: string) => {
    const message = text.trim();
    if (!message || sending) return;
    setInput('');
    setMessages((m) => [...m, { id: nextId(), role: 'me', text: message }]);

    if (mode === 'local') {
      const mem = memRef.current ?? { facts: [], prefs: [], nextId: 1 };
      const { answer, mem: next } = respond(message, mem);
      memRef.current = next;
      saveMemory(next);
      setMessages((m) => [...m, { id: nextId(), role: 'devy', text: answer.text, result: { label: answer.label, text: answer.text } }]);
      setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 50);
      return;
    }

    setSending(true);
    try {
      const result = await ask(base, message);
      setMessages((m) => [...m, { id: nextId(), role: 'devy', text: result.text, result }]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        {
          id: nextId(),
          role: 'error',
          text:
            (e instanceof Error ? e.message : String(e)) +
            '\n\nCheck the server address (⚙︎) and that your phone can reach it — or switch to On-phone mode, which needs no server.',
        },
      ]);
    } finally {
      setSending(false);
      setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 50);
    }
  };

  const renderMsg = ({ item }: { item: Msg }) => {
    if (item.role === 'me') {
      return (
        <View style={[styles.bubble, styles.me]}>
          <Text style={styles.msgText}>{item.text}</Text>
        </View>
      );
    }
    if (item.role === 'error') {
      return (
        <View style={[styles.bubble, styles.bot]}>
          <Text style={[styles.msgText, { color: C.err }]}>{item.text}</Text>
        </View>
      );
    }
    const r = item.result;
    const label = r?.label ?? '';
    const open = !!expanded[item.id];
    return (
      <View style={[styles.bubble, styles.bot]}>
        {!!label && (
          <View style={[styles.labelPill, { borderColor: labelColor(label) }]}>
            <Text style={[styles.labelText, { color: labelColor(label) }]}>{label}</Text>
          </View>
        )}
        <Text style={styles.msgText}>{item.text}</Text>
        {r?.route && (
          <Pressable onPress={() => setExpanded((e) => ({ ...e, [item.id]: !open }))}>
            <Text style={styles.why}>{open ? 'hide why' : 'why?'}</Text>
          </Pressable>
        )}
        {open && r?.route && (
          <View style={styles.whyBox}>
            <Text style={styles.whyText}>
              Route: {r.route.kind} ({r.route.depth}), because {r.route.reason}
            </Text>
            <Text style={styles.whyText}>Drawers: {(r.drawers ?? []).join(', ') || 'none'}</Text>
            {(r.evidence ?? []).map((ev, i) => (
              <Text key={i} style={styles.evText}>
                • {ev}
              </Text>
            ))}
          </View>
        )}
      </View>
    );
  };

  const quick = mode === 'local' ? QUICK_LOCAL : QUICK_SERVER;

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 8 : 0}
    >
      <View style={styles.modeRow}>
        {(['server', 'local'] as Mode[]).map((mo) => (
          <Pressable key={mo} style={[styles.modeBtn, mode === mo && styles.modeActive]} onPress={() => setMode(mo)}>
            <Text style={[styles.modeText, mode === mo && styles.modeTextActive]}>
              {mo === 'server' ? 'Server' : 'On-phone'}
            </Text>
          </Pressable>
        ))}
      </View>
      {mode === 'local' && (
        <Text style={styles.banner}>Running on your phone — no server, no big model. Remembers facts and knows boards.</Text>
      )}

      <FlatList
        ref={listRef}
        style={styles.flex}
        contentContainerStyle={styles.listContent}
        data={messages}
        keyExtractor={(m) => m.id}
        renderItem={renderMsg}
        ListEmptyComponent={
          <Text style={styles.empty}>
            {mode === 'local'
              ? 'This runs on your phone. Tell me facts to remember, ask how to program a board, or ask what a chip is. For general questions, switch to Server.'
              : 'Ask about your hardware, tell Devy something to remember, or type /help. Every answer says where it came from.'}
          </Text>
        }
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: false })}
      />
      <View style={styles.quickRow}>
        {quick.map((q) => (
          <Pressable key={q} style={styles.chip} onPress={() => send(q)} disabled={sending}>
            <Text style={styles.chipText}>{q}</Text>
          </Pressable>
        ))}
      </View>
      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder={mode === 'local' ? 'ask or tell me (on your phone)…' : 'ask or tell me something…'}
          placeholderTextColor={C.muted}
          editable={!sending}
          onSubmitEditing={() => send(input)}
          returnKeyType="send"
        />
        <Pressable
          style={[styles.btn, styles.btnPrimary, sending && styles.btnDisabled]}
          onPress={() => send(input)}
          disabled={sending}
        >
          {sending ? <ActivityIndicator color="#042" /> : <Text style={styles.btnPrimaryText}>Send</Text>}
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  modeRow: { flexDirection: 'row', gap: 8, padding: 10, paddingBottom: 4 },
  modeBtn: { flex: 1, paddingVertical: 7, borderRadius: 999, borderWidth: 1, borderColor: C.border, alignItems: 'center', backgroundColor: C.panel2 },
  modeActive: { backgroundColor: C.accent, borderColor: 'transparent' },
  modeText: { color: C.muted, fontSize: 13, fontWeight: '600' },
  modeTextActive: { color: '#042' },
  banner: { color: C.ok, fontSize: 12, textAlign: 'center', paddingHorizontal: 12, paddingBottom: 4 },
  listContent: { padding: 12, gap: 10, flexGrow: 1 },
  empty: { color: C.muted, fontSize: 14, lineHeight: 21, padding: 16, textAlign: 'center' },
  bubble: { maxWidth: '92%', padding: 10, borderRadius: 12, borderWidth: 1, borderColor: C.border },
  me: { alignSelf: 'flex-end', backgroundColor: C.panel2 },
  bot: { alignSelf: 'flex-start', backgroundColor: C.panel },
  msgText: { color: C.text, fontSize: 15, lineHeight: 21 },
  labelPill: { alignSelf: 'flex-start', borderWidth: 1, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 1, marginBottom: 6 },
  labelText: { fontSize: 11, fontWeight: '700' },
  why: { color: C.muted, fontSize: 12, marginTop: 8 },
  whyBox: { marginTop: 6, paddingTop: 6, borderTopWidth: 1, borderTopColor: C.border },
  whyText: { color: C.muted, fontSize: 12, marginBottom: 2 },
  evText: { color: C.muted, fontSize: 11, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  quickRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, paddingHorizontal: 12, paddingBottom: 6 },
  chip: { borderWidth: 1, borderColor: C.border, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6, backgroundColor: C.panel2 },
  chipText: { color: C.text, fontSize: 13 },
  inputRow: { flexDirection: 'row', gap: 8, padding: 12, borderTopWidth: 1, borderTopColor: C.border, backgroundColor: C.panel, alignItems: 'center' },
  input: { flex: 1, backgroundColor: C.bg, color: C.text, borderWidth: 1, borderColor: C.border, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10, fontSize: 15 },
  btn: { borderWidth: 1, borderColor: C.border, borderRadius: 8, paddingHorizontal: 14, paddingVertical: 10, backgroundColor: C.panel2 },
  btnPrimary: { backgroundColor: C.accent, borderColor: 'transparent' },
  btnPrimaryText: { color: '#042', fontWeight: '700', fontSize: 14 },
  btnDisabled: { opacity: 0.6 },
});
