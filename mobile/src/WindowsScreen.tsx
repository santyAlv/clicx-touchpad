import { Ionicons } from '@expo/vector-icons';
import { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { ClicxMessage } from './protocol';
import { ScreenChrome } from './screenChrome';
import { THEME } from './theme';
import { type Palette, useStyles, useTheme } from './palette';

type Props = {
  send: (msg: ClicxMessage) => void;
  onReply: (cb: (data: Record<string, unknown>) => void) => () => void;
  onBack: () => void;
};

type Win = { id: number; title: string; app: string; active: boolean; minimized: boolean };

const POLL_MS = 2000;

/** Centro de control → Ventanas. Lista, foco, minimizar/maximizar/restaurar, cerrar. */
export function WindowsScreen({ send, onReply, onBack }: Props) {
  const { THEME } = useTheme();
  const styles = useStyles(makeStyles);
  const [wins, setWins] = useState<Win[]>([]);
  const [loading, setLoading] = useState(true);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const stop = onReply((data) => {
      if (data?.t === 'windows' && data?.action === 'list' && Array.isArray(data.windows)) {
        setWins(data.windows as Win[]);
        setLoading(false);
      }
    });
    return stop;
  }, [onReply]);

  useEffect(() => {
    send({ t: 'windows', action: 'list' });
    timer.current = setInterval(() => send({ t: 'windows', action: 'list', force: false }), POLL_MS);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [send]);

  const act = (action: 'focus' | 'minimize' | 'maximize' | 'restore' | 'close', id: number) => {
    send({ t: 'windows', action, id });
    // Refresh shortly after to reflect the change.
    setTimeout(() => send({ t: 'windows', action: 'list', force: true }), 250);
  };

  return (
    <ScreenChrome
      title="Ventanas"
      subtitle={wins.length ? `${wins.length} ventana(s)` : 'Las ventanas del sistema no se listan'}
      onBack={onBack}
    >
      {wins.length === 0 && !loading ? (
        <Text style={styles.empty}>No hay ventanas abiertas.</Text>
      ) : null}

      {wins.map((w) => (
        <View
          key={w.id}
          style={[styles.win, w.active && styles.winActive]}
        >
          <View style={styles.winInfo}>
            <View style={styles.titleRow}>
              <Text style={styles.title} numberOfLines={1}>
                {w.title}
              </Text>
              {w.active ? <View style={styles.activeDot} /> : null}
            </View>
            <Text style={styles.app} numberOfLines={1}>
              {w.app || 'Aplicación'}
            </Text>
          </View>
          <View style={styles.actions}>
            {w.minimized ? (
              <IconBtn icon="return-down-back" label="Restaurar" onPress={() => act('restore', w.id)} />
            ) : (
              <>
                <IconBtn icon="scan-outline" label="Minimizar" onPress={() => act('minimize', w.id)} />
                <IconBtn icon="expand-outline" label="Maximizar" onPress={() => act('maximize', w.id)} />
              </>
            )}
            <IconBtn icon="open-outline" label="Primer plano" onPress={() => act('focus', w.id)} />
            <IconBtn icon="close-outline" label="Cerrar" danger onPress={() => act('close', w.id)} />
          </View>
        </View>
      ))}
    </ScreenChrome>
  );
}

function IconBtn({
  icon,
  label,
  onPress,
  danger,
}: {
  icon: string;
  label: string;
  onPress: () => void;
  danger?: boolean;
}) {
  const { THEME } = useTheme();
  const styles = useStyles(makeStyles);
  return (
    <Pressable style={styles.iconBtn} onPress={onPress} accessibilityLabel={label}>
      <Ionicons
        name={icon as keyof typeof Ionicons.glyphMap}
        size={18}
        color={danger ? THEME.red : THEME.label}
      />
    </Pressable>
  );
}

const makeStyles = ({ THEME }: Palette) =>
  StyleSheet.create({
    empty: {
      color: THEME.tertiary,
      fontSize: 13,
      textAlign: 'center',
      marginTop: 20,
    },
    win: {
      backgroundColor: THEME.surface,
      borderRadius: 16,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: THEME.hairline,
      padding: 14,
      marginBottom: 10,
    },
    winActive: {
      borderColor: THEME.orange,
    },
    winInfo: {
      marginBottom: 10,
      gap: 3,
    },
    titleRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
    },
    title: {
      flex: 1,
      color: THEME.label,
      fontSize: 14,
      fontWeight: '600',
    },
    activeDot: {
      width: 8,
      height: 8,
      borderRadius: 4,
      backgroundColor: THEME.orange,
    },
    app: {
      color: THEME.secondary,
      fontSize: 11,
    },
    actions: {
      flexDirection: 'row',
      gap: 8,
      flexWrap: 'wrap',
    },
    iconBtn: {
      width: 40,
      height: 36,
      borderRadius: 10,
      backgroundColor: THEME.surface2,
      alignItems: 'center',
      justifyContent: 'center',
    },
  });
