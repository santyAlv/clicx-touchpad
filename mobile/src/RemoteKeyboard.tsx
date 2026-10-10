import { useEffect, useRef, useState } from 'react';
import {
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
  type TextInput as TextInputType,
} from 'react-native';
import type { ClicxMessage } from './protocol';
import { THEME } from './theme';
import { type Palette, useStyles, useTheme } from './palette';

type Props = {
  visible: boolean;
  onClose: () => void;
  send: (msg: ClicxMessage) => void;
};

/** Diff that handles IME / voice dictation replacements. */
function textDiff(prev: string, next: string): { deleteCount: number; insert: string } {
  let start = 0;
  const minLen = Math.min(prev.length, next.length);
  while (start < minLen && prev[start] === next[start]) start++;

  let endPrev = prev.length - 1;
  let endNext = next.length - 1;
  while (
    endPrev >= start &&
    endNext >= start &&
    prev[endPrev] === next[endNext]
  ) {
    endPrev--;
    endNext--;
  }

  return {
    deleteCount: Math.max(0, endPrev - start + 1),
    insert: next.slice(start, endNext + 1),
  };
}

/** Soft keyboard bridge — types into the PC focused field. */
export function RemoteKeyboard({ visible, onClose, send }: Props) {
  const { THEME } = useTheme();
  const styles = useStyles(makeStyles);
  const [value, setValue] = useState('');
  const prevRef = useRef('');
  const inputRef = useRef<TextInputType>(null);
  const flushTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingRef = useRef<string | null>(null);

  useEffect(() => {
    if (!visible) {
      setValue('');
      prevRef.current = '';
      pendingRef.current = null;
      if (flushTimer.current) clearTimeout(flushTimer.current);
      return;
    }
    const t = setTimeout(() => inputRef.current?.focus(), 80);
    return () => clearTimeout(t);
  }, [visible]);

  const applyDiff = (prev: string, next: string) => {
    const { deleteCount, insert } = textDiff(prev, next);
    for (let i = 0; i < deleteCount; i++) {
      send({ t: 'key', name: 'backspace' });
    }
    if (insert) {
      send({ t: 'type', text: insert });
    }
  };

  /** Debounce rapid voice/IME updates so we send the stable string. */
  const onChangeText = (next: string) => {
    setValue(next);
    pendingRef.current = next;
    if (flushTimer.current) clearTimeout(flushTimer.current);
    flushTimer.current = setTimeout(() => {
      flushTimer.current = null;
      const pending = pendingRef.current;
      if (pending == null) return;
      const prev = prevRef.current;
      if (pending === prev) return;
      applyDiff(prev, pending);
      prevRef.current = pending;
      pendingRef.current = null;
    }, 120);
  };

  if (!visible) return null;

  return (
    <View style={styles.wrap}>
      <View style={styles.bar}>
        <Text style={styles.title}>Teclado</Text>
        <Pressable
          onPress={() => {
            if (flushTimer.current) {
              clearTimeout(flushTimer.current);
              flushTimer.current = null;
            }
            const pending = pendingRef.current;
            if (pending != null && pending !== prevRef.current) {
              applyDiff(prevRef.current, pending);
              prevRef.current = pending;
            }
            onClose();
          }}
          hitSlop={10}
          style={styles.closeBtn}
        >
          <Text style={styles.closeText}>Cerrar</Text>
        </Pressable>
      </View>
      <TextInput
        ref={inputRef}
        style={styles.input}
        value={value}
        onChangeText={onChangeText}
        placeholder="Escribí o dictá acá…"
        placeholderTextColor={THEME.tertiary}
        autoFocus
        blurOnSubmit={false}
        returnKeyType="default"
        multiline
        onSubmitEditing={() => send({ t: 'key', name: 'enter' })}
        autoCorrect
        autoCapitalize="sentences"
        textContentType="none"
      />
      <View style={styles.keys}>
        {(
          [
            ['Tab', 'tab'],
            ['Enter', 'enter'],
            ['⌫', 'backspace'],
            ['Esc', 'esc'],
          ] as const
        ).map(([label, name]) => (
          <Pressable
            key={name}
            style={styles.keyChip}
            onPress={() => send({ t: 'key', name })}
          >
            <Text style={styles.keyText}>{label}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

const makeStyles = ({ THEME }: Palette) =>
  StyleSheet.create({
    wrap: {
      backgroundColor: THEME.canvasRaised,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: THEME.hairline,
      paddingHorizontal: 14,
      paddingTop: 10,
      paddingBottom: 12,
      gap: 10,
    },
    bar: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
    },
    title: {
      color: THEME.label,
      fontSize: 13,
      fontWeight: '600',
      letterSpacing: -0.2,
    },
    closeBtn: {
      paddingVertical: 4,
      paddingHorizontal: 8,
    },
    closeText: {
      color: THEME.blueBright,
      fontSize: 13,
      fontWeight: '600',
    },
    input: {
      backgroundColor: THEME.canvas,
      borderRadius: 12,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: THEME.hairline,
      color: THEME.label,
      fontSize: 16,
      paddingHorizontal: 14,
      paddingVertical: 12,
      minHeight: 48,
      maxHeight: 120,
    },
    keys: {
      flexDirection: 'row',
      justifyContent: 'center',
      gap: 8,
    },
    keyChip: {
      paddingHorizontal: 14,
      paddingVertical: 8,
      borderRadius: 12,
      backgroundColor: THEME.surface,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: THEME.hairline,
    },
    keyText: {
      color: THEME.label,
      fontSize: 12,
      fontWeight: '600',
    },
  });
