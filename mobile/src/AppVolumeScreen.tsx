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

type AppVolume = { id: number; name: string; volume: number; muted: boolean };

const POLL_MS = 3000;

/** Centro de control → Volumen por aplicación. Independiente del volumen general. */
export function AppVolumeScreen({ send, onReply, onBack }: Props) {
  const { THEME } = useTheme();
  const styles = useStyles(makeStyles);
  const [apps, setApps] = useState<AppVolume[]>([]);
  const [loading, setLoading] = useState(true);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const stop = onReply((data) => {
      if (data?.t === 'app_volume' && data?.action === 'list' && Array.isArray(data.apps)) {
        setApps(data.apps as AppVolume[]);
        setLoading(false);
      }
    });
    return stop;
  }, [onReply]);

  useEffect(() => {
    send({ t: 'app_volume', action: 'list' });
    timer.current = setInterval(
      () => send({ t: 'app_volume', action: 'list' }),
      POLL_MS,
    );
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [send]);

  const refresh = () => {
    setLoading(true);
    send({ t: 'app_volume', action: 'list' });
    setTimeout(() => setLoading(false), 400);
  };

  const setVol = (id: number, next: number) => {
    const clamped = Math.max(0, Math.min(100, next));
    setApps((prev) =>
      prev.map((a) => (a.id === id ? { ...a, volume: clamped } : a)),
    );
    send({ t: 'app_volume', action: 'set', id, volume: clamped });
  };

  const toggleMute = (app: AppVolume) => {
    const next = !app.muted;
    setApps((prev) =>
      prev.map((a) => (a.id === app.id ? { ...a, muted: next } : a)),
    );
    send({ t: 'app_volume', action: 'mute', id: app.id, muted: next });
  };

  return (
    <ScreenChrome
      title="Volumen por app"
      subtitle={apps.length ? `${apps.length} sesión(es) de audio` : 'Volumen general no afectado'}
      onBack={onBack}
    >
      <View style={styles.topRow}>
        <Text style={styles.note}>
          Ajusta cada aplicación por separado. El volumen general se mantiene intacto.
        </Text>
        <Pressable style={styles.refreshBtn} onPress={refresh}>
          <Ionicons
            name={loading ? 'sync' : 'refresh-outline'}
            size={16}
            color={THEME.label}
          />
          <Text style={styles.refreshText}>Actualizar</Text>
        </Pressable>
      </View>

      {apps.length === 0 && !loading ? (
        <Text style={styles.empty}>No hay aplicaciones reproduciendo audio.</Text>
      ) : null}

      {apps.map((app) => {
        const muted = app.muted;
        const pct = Math.round(app.volume);
        return (
          <View key={app.id} style={[styles.app, muted && styles.appMuted]}>
            <View style={styles.appHead}>
              <Pressable
                style={styles.muteBtn}
                onPress={() => toggleMute(app)}
                accessibilityLabel={muted ? 'Desilenciar' : 'Silenciar'}
              >
                <Ionicons
                  name={muted ? 'volume-mute-outline' : 'volume-medium-outline'}
                  size={20}
                  color={muted ? THEME.red : THEME.label}
                />
              </Pressable>
              <Text style={styles.appName} numberOfLines={1}>
                {app.name}
              </Text>
              <Text style={styles.pct}>{pct}%</Text>
            </View>
            <View style={styles.slider}>
              <Pressable
                style={styles.step}
                onPress={() => setVol(app.id, app.volume - 10)}
                disabled={muted}
              >
                <Ionicons name="remove" size={18} color={THEME.label} />
              </Pressable>
              <View style={styles.bar}>
                <View
                  style={[styles.barFill, { width: `${pct}%` }]}
                />
              </View>
              <Pressable
                style={styles.step}
                onPress={() => setVol(app.id, app.volume + 10)}
                disabled={muted}
              >
                <Ionicons name="add" size={18} color={THEME.label} />
              </Pressable>
            </View>
          </View>
        );
      })}
    </ScreenChrome>
  );
}

const makeStyles = ({ THEME }: Palette) =>
  StyleSheet.create({
    topRow: {
      marginBottom: 12,
      gap: 10,
    },
    note: {
      color: THEME.secondary,
      fontSize: 12,
      lineHeight: 17,
    },
    refreshBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      alignSelf: 'flex-end',
      paddingHorizontal: 12,
      paddingVertical: 7,
      borderRadius: 12,
      backgroundColor: THEME.surface,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: THEME.hairline,
    },
    refreshText: {
      color: THEME.label,
      fontSize: 12,
      fontWeight: '600',
    },
    empty: {
      color: THEME.tertiary,
      fontSize: 13,
      textAlign: 'center',
      marginTop: 20,
    },
    app: {
      backgroundColor: THEME.surface,
      borderRadius: 16,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: THEME.hairline,
      padding: 14,
      marginBottom: 10,
    },
    appMuted: {
      opacity: 0.6,
    },
    appHead: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 10,
      marginBottom: 10,
    },
    muteBtn: {
      width: 36,
      height: 36,
      borderRadius: 18,
      backgroundColor: THEME.surface2,
      alignItems: 'center',
      justifyContent: 'center',
    },
    appName: {
      flex: 1,
      color: THEME.label,
      fontSize: 14,
      fontWeight: '600',
    },
    pct: {
      color: THEME.secondary,
      fontSize: 12,
      fontWeight: '600',
      minWidth: 40,
      textAlign: 'right',
    },
    slider: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 10,
    },
    step: {
      width: 34,
      height: 34,
      borderRadius: 10,
      backgroundColor: THEME.surface2,
      alignItems: 'center',
      justifyContent: 'center',
    },
    bar: {
      flex: 1,
      height: 8,
      borderRadius: 4,
      backgroundColor: THEME.canvas,
      overflow: 'hidden',
    },
    barFill: {
      height: 8,
      borderRadius: 4,
      backgroundColor: THEME.orange,
    },
  });
