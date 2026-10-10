import { Ionicons } from '@expo/vector-icons';
import { useState } from 'react';
import {
  Pressable,
  StyleSheet,
  Text,
  View,
  Modal,
  Platform,
} from 'react-native';
import type { ClicxMessage } from './protocol';
import { RemoteKeyboard } from './RemoteKeyboard';
import { ScreenChrome } from './screenChrome';
import { THEME } from './theme';
import { type Palette, useStyles, useTheme } from './palette';

type Props = {
  send: (msg: ClicxMessage) => void;
  onBack: () => void;
};

const FN_KEYS = ['F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7', 'F8', 'F9', 'F10', 'F11', 'F12'];

const NAV: { label: string; name: string }[] = [
  { label: '↑', name: 'up' },
  { label: '↓', name: 'down' },
  { label: '←', name: 'left' },
  { label: '→', name: 'right' },
  { label: 'Home', name: 'home' },
  { label: 'End', name: 'end' },
  { label: 'Re Pág', name: 'pageup' },
  { label: 'Av Pág', name: 'pagedown' },
];

const SHORTCUTS: { label: string; keys: string[] }[] = [
  { label: 'Copiar', keys: ['ctrl', 'c'] },
  { label: 'Pegar', keys: ['ctrl', 'v'] },
  { label: 'Cortar', keys: ['ctrl', 'x'] },
  { label: 'Deshacer', keys: ['ctrl', 'z'] },
  { label: 'Guardar', keys: ['ctrl', 's'] },
  { label: 'Seleccionar todo', keys: ['ctrl', 'a'] },
];

/** Centro de control → Teclado. Extiende RemoteKeyboard (mismo protocolo t:type/key/hotkey). */
export function KeyboardScreen({ send, onBack }: Props) {
  const { THEME } = useTheme();
  const styles = useStyles(makeStyles);
  const [showText, setShowText] = useState(false);

  const key = (name: string) => send({ t: 'key', name });
  const hot = (keys: string[]) => send({ t: 'hotkey', keys });

  return (
    <ScreenChrome title="Teclado" subtitle="F1–F12, atajos y escritura" onBack={onBack}>
      <Pressable style={styles.textToggle} onPress={() => setShowText(true)}>
        <Ionicons name="keypad-outline" size={16} color={THEME.label} />
        <Text style={styles.textToggleLabel}>Abrir teclado de escritura / dictado</Text>
      </Pressable>

      <Text style={styles.section}>Teclas de función</Text>
      <View style={styles.fnRow}>
        {FN_KEYS.map((f) => (
          <Pressable key={f} style={styles.fnKey} onPress={() => key(f.toLowerCase())}>
            <Text style={styles.fnText}>{f}</Text>
          </Pressable>
        ))}
      </View>

      <Text style={styles.section}>Navegación</Text>
      <View style={styles.navGrid}>
        {NAV.map((n) => (
          <Pressable key={n.name} style={styles.key} onPress={() => key(n.name)}>
            <Text style={styles.keyText}>{n.label}</Text>
          </Pressable>
        ))}
      </View>

      <Text style={styles.section}>Atajos</Text>
      <View style={styles.shortcutGrid}>
        {SHORTCUTS.map((s) => (
          <Pressable
            key={s.label}
            style={styles.shortcut}
            onPress={() => hot(s.keys)}
          >
            <Text style={styles.shortcutText}>{s.label}</Text>
          </Pressable>
        ))}
      </View>

      <View style={styles.spacer} />

      <Modal
        visible={showText}
        transparent
        animationType="slide"
        onRequestClose={() => setShowText(false)}
      >
        <View style={styles.modal}>
          <View style={styles.keyboard}>
            <RemoteKeyboard visible send={send} onClose={() => setShowText(false)} />
          </View>
        </View>
      </Modal>
    </ScreenChrome>
  );
}

const makeStyles = ({ THEME }: Palette) =>
  StyleSheet.create({
    textToggle: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
      backgroundColor: THEME.surface,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: THEME.hairline,
      borderRadius: 12,
      padding: 12,
      marginBottom: 8,
    },
    textToggleLabel: {
      color: THEME.label,
      fontSize: 13,
      fontWeight: '600',
    },
    section: {
      color: THEME.secondary,
      fontSize: 12,
      fontWeight: '600',
      marginTop: 14,
      marginBottom: 8,
    },
    fnRow: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 8,
    },
    fnKey: {
      width: '15%',
      minWidth: 48,
      paddingVertical: 14,
      borderRadius: 12,
      backgroundColor: THEME.surface,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: THEME.hairline,
      alignItems: 'center',
    },
    fnText: {
      color: THEME.label,
      fontSize: 12,
      fontWeight: '600',
    },
    navGrid: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 8,
    },
    key: {
      minWidth: 64,
      paddingVertical: 14,
      paddingHorizontal: 12,
      borderRadius: 12,
      backgroundColor: THEME.surface,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: THEME.hairline,
      alignItems: 'center',
    },
    keyText: {
      color: THEME.label,
      fontSize: 13,
      fontWeight: '600',
    },
    shortcutGrid: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 8,
    },
    shortcut: {
      paddingHorizontal: 14,
      paddingVertical: 10,
      borderRadius: 12,
      backgroundColor: THEME.surface2,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: THEME.hairline,
    },
    shortcutText: {
      color: THEME.label,
      fontSize: 12,
      fontWeight: '600',
    },
    spacer: {
      height: 8,
    },
    modal: {
      flex: 1,
      backgroundColor: 'rgba(0,0,0,0.4)',
      justifyContent: 'flex-end',
    },
    keyboard: {
      backgroundColor: THEME.canvas,
      paddingBottom: Platform.OS === 'ios' ? 24 : 8,
    },
  });
