// The chat with Devy. Talks to /api/brain/ask and shows labeled answers with a "why?".

import { useRef, useState } from 'react';
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
import { C, labelColor } from './theme';

const QUICK = ["What's plugged in?", 'How do I program my Pico?', '/help'];

type Msg = { id: string; role: 'me' | 'devy' | 'error'; text: string; result?: AskResult };
let counter = 0;
const nextId = () => `${Date.now()}-${counter++}`;

export default function Chat({ base }: { base: string }) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const listRef = useRef<FlatList<Msg>>(null);

  const send = async (text: string) => {
    const message = text.trim();
    if (!message || sending) return;
    setInput('');
    setMessages((m) => [...m, { id: nextId(), role: 'me', text: message }]);
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
            '\n\nCheck the server address (⚙︎), that the app runs with --host 0.0.0.0, and that your ' +
            'phone can reach it (same Wi-Fi, or Tailscale on).',
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

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 8 : 0}
    >
      <FlatList
        ref={listRef}
        style={styles.flex}
        contentContainerStyle={styles.listContent}
        data={messages}
        keyExtractor={(m) => m.id}
        renderItem={renderMsg}
        ListEmptyComponent={
          <Text style={styles.empty}>
            Ask about your hardware, tell Devy something to remember, or type /help. Every answer says where
            it came from. Devy runs on your computer; this is just the screen.
          </Text>
        }
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: false })}
      />
      <View style={styles.quickRow}>
        {QUICK.map((q) => (
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
          placeholder="ask or tell me something…"
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
  inputRow: {
    flexDirection: 'row',
    gap: 8,
    padding: 12,
    borderTopWidth: 1,
    borderTopColor: C.border,
    backgroundColor: C.panel,
    alignItems: 'center',
  },
  input: {
    flex: 1,
    backgroundColor: C.bg,
    color: C.text,
    borderWidth: 1,
    borderColor: C.border,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
  },
  btn: { borderWidth: 1, borderColor: C.border, borderRadius: 8, paddingHorizontal: 14, paddingVertical: 10, backgroundColor: C.panel2 },
  btnPrimary: { backgroundColor: C.accent, borderColor: 'transparent' },
  btnPrimaryText: { color: '#042', fontWeight: '700', fontSize: 14 },
  btnDisabled: { opacity: 0.6 },
});
