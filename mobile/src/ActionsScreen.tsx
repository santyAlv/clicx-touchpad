import { Ionicons } from '@expo/vector-icons';
import { useState } from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import type { ClicxMessage } from './protocol';
import { ScreenChrome } from './screenChrome';
import { THEME } from './theme';
import { type Palette, useStyles, useTheme } from './palette';

type Props = {
  send: (msg: ClicxMessage) => void;
  onBack: () => void;
};

type ActionItem = {
  key: string;
  label: string;
  icon: string;
  color: string;
  dangerous: boolean;
};

const ACTIONS: ActionItem[] = [
  { key: 'desktop', label: 'Escritorio', icon: 'desktop-outline', color: THEME.teal, dangerous: false },
  { key: 'screenshot', label: 'Captura de pantalla', icon: 'camera-outline', color: THEME.purple, dangerous: false },
  { key: 'lock', label: 'Bloquear', icon: 'lock-closed-outline', color: THEME.blueBright, dangerous: true },
  { key: 'sleep', label: 'Suspender', icon: 'moon-outline', color: THEME.indigo, dangerous: true },
  { key: 'logout', label: 'Cerrar sesión', icon: 'log-out-outline', color: THEME.orange, dangerous: true },
  { key: 'restart', label: 'Reiniciar', icon: 'refresh-outline', color: THEME.red, dangerous: true },
  { key: 'shutdown', label: 'Apagar', icon: 'power-outline', color: THEME.red, dangerous: true },
];

/** Control Center → Acciones. Dangerous actions use dual confirmation (UI + host). */
export function ActionsScreen({ send, onBack }: Props) {
  const { THEME } = useTheme();
  const styles = useStyles(makeStyles);
  const [pending, setPending] = useState<ActionItem | null>(null);
  const [busy, setBusy] = useState(false);

  const run = (item: ActionItem, confirm: boolean) => {
    setPending(null);
    if (item.dangerous) {
      // Host-side double confirmation: prepare (arm) then go (within window).
      send({ t: 'action', name: item.key, confirm: 'prepare' });
      send({ t: 'action', name: item.key, confirm: 'go' });
    } else {
      send({ t: 'action', name: item.key });
    }
  };

  const tap = (item: ActionItem) => {
    if (item.dangerous) {
      setPending(item);
      return;
    }
    setBusy(true);
    run(item, false);
    setTimeout(() => setBusy(false), 300);
  };

  return (
    <ScreenChrome title="Acciones" subtitle="Doble confirmación en la PC" onBack={onBack}>
      <Text style={styles.hint}>
        Las acciones con riesgo te piden confirmación acá y en la PC (ventana de unos segundos).
      </Text>
      <View style={styles.grid}>
        {ACTIONS.map((a) => (
          <Pressable
            key={a.key}
            style={({ pressed }) => [
              styles.action,
              pressed && styles.actionPressed,
            ]}
            onPress={() => tap(a)}
          >
            <Ionicons
              name={a.icon as keyof typeof Ionicons.glyphMap}
              size={22}
              color={a.color}
            />
            <Text style={[styles.actionLabel, a.dangerous && { color: a.color }]}>
              {a.label}
            </Text>
          </Pressable>
        ))}
      </View>

      <Modal visible={!!pending} transparent animationType="fade" onRequestClose={() => setPending(null)}>
        <View style={styles.backdrop}>
          <View style={styles.sheet}>
            <Text style={styles.confirmTitle}>¿{pending?.label} la PC?</Text>
            <Text style={styles.confirmHint}>
              La acción se ejecuta en unos segundos. También tenés que confirmarla en la PC.
            </Text>
            <View style={styles.confirmRow}>
              <Pressable style={[styles.btn, styles.cancel]} onPress={() => setPending(null)}>
                <Text style={styles.cancelText}>Cancelar</Text>
              </Pressable>
              <Pressable
                style={[styles.btn, styles.go]}
                onPress={() => run(pending as ActionItem, true)}
              >
                <Text style={styles.goText}>Confirmar</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
      {busy ? null : null}
    </ScreenChrome>
  );
}

const makeStyles = ({ THEME }: Palette) =>
  StyleSheet.create({
    hint: {
      color: THEME.secondary,
      fontSize: 12,
      lineHeight: 17,
      marginBottom: 14,
    },
    grid: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 10,
    },
    action: {
      flexBasis: '31%',
      flexGrow: 1,
      minHeight: 84,
      borderRadius: 16,
      backgroundColor: THEME.surface,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: THEME.hairline,
      alignItems: 'center',
      justifyContent: 'center',
      gap: 8,
      padding: 10,
    },
    actionPressed: {
      backgroundColor: THEME.surface2,
    },
    actionLabel: {
      color: THEME.label,
      fontSize: 12,
      fontWeight: '600',
      textAlign: 'center',
    },
    backdrop: {
      flex: 1,
      backgroundColor: 'rgba(0,0,0,0.6)',
      justifyContent: 'center',
      padding: 32,
    },
    sheet: {
      backgroundColor: THEME.canvasRaised,
      borderRadius: 20,
      padding: 20,
      gap: 12,
    },
    confirmTitle: {
      color: THEME.label,
      fontSize: 17,
      fontWeight: '600',
    },
    confirmHint: {
      color: THEME.secondary,
      fontSize: 13,
      lineHeight: 18,
    },
    confirmRow: {
      flexDirection: 'row',
      gap: 10,
      marginTop: 4,
    },
    btn: {
      flex: 1,
      paddingVertical: 12,
      borderRadius: 12,
      alignItems: 'center',
    },
    cancel: {
      backgroundColor: THEME.surface,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: THEME.hairline,
    },
    cancelText: {
      color: THEME.label,
      fontWeight: '600',
    },
    go: {
      backgroundColor: THEME.red,
    },
    goText: {
      color: '#FFFFFF',
      fontWeight: '600',
    },
  });
