import { Ionicons } from '@expo/vector-icons';
import { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { ClicxMessage } from './protocol';
import { GlassCard, ScreenChrome } from './screenChrome';
import { THEME } from './theme';
import { type Palette, useStyles, useTheme } from './palette';

type Props = {
  send: (msg: ClicxMessage) => void;
  onReply: (cb: (data: Record<string, unknown>) => void) => () => void;
  onBack: () => void;
};

type Status =
  | Record<string, unknown>
  | { battery?: { percent?: number; plugged?: boolean } | null }
  | { cpu?: { percent?: number; cores?: number } | null }
  | { ram?: { total?: number; used?: number; percent?: number } | null };

const POLL_MS = 2000;

function pct(n: unknown): string {
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—';
  return `${Math.round(n)}%`;
}

function fmtBytes(n: unknown): string {
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—';
  const gb = n / 1024 ** 3;
  return `${gb.toFixed(1)} GB`;
}

/** PC status: battery / CPU / RAM / disk / network / uptime. Polls with throttle. */
export function SystemScreen({ send, onReply, onBack }: Props) {
  const { THEME } = useTheme();
  const styles = useStyles(makeStyles);
  const [status, setStatus] = useState<Status | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const stop = onReply((data) => {
      if (data?.t === 'status') setStatus(data);
    });
    return stop;
  }, [onReply]);

  useEffect(() => {
    send({ t: 'status', get: true });
    timer.current = setInterval(() => send({ t: 'status', get: true }), POLL_MS);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [send]);

  const refresh = () => {
    setRefreshing(true);
    send({ t: 'status', get: true });
    setTimeout(() => setRefreshing(false), 400);
  };

  const r = ((status ?? {}) as Record<string, any>);
  const battery = r.battery as any;
  const cpu = r.cpu as any;
  const ram = r.ram as any;

  return (
    <ScreenChrome title="Estado de la PC" subtitle="Actualiza cada 2 s" onBack={onBack}>
      <View style={styles.actions}>
        <Pressable style={styles.refreshBtn} onPress={refresh}>
          <Ionicons
            name={refreshing ? 'sync' : 'refresh-outline'}
            size={16}
            color={THEME.label}
          />
          <Text style={styles.refreshText}>Actualizar</Text>
        </Pressable>
      </View>

      <Text style={styles.hostLine}>{String(r.ip ?? '')}</Text>

      <Card icon="battery-half-outline" label="Batería">
        <Grid>
          <Cell label="Carga" value={battery ? pct(battery.percent) : '—'} />
          <Cell
            label="Alimentación"
            value={battery ? (battery.plugged ? 'Corriente' : 'Batería') : '—'}
          />
        </Grid>
      </Card>

      <Card icon="hardware-chip-outline" label="CPU">
        <Grid>
          <Cell label="Uso" value={cpu ? pct(cpu.percent) : '—'} />
          <Cell label="Núcleos" value={cpu && typeof cpu.cores === 'number' ? String(cpu.cores) : '—'} />
        </Grid>
      </Card>

      <Card icon="hardware-chip-outline" label="Memoria RAM">
        <Grid>
          <Cell label="Uso" value={ram ? pct(ram.percent) : '—'} />
          <Cell label="Usada" value={ram ? fmtBytes(ram.used) : '—'} />
        </Grid>
      </Card>

      <Card icon="save-outline" label="Disco (C:)">
        <Grid>
          <Cell label="Uso" value={r.disk ? pct((r.disk as any).percent) : '—'} />
          <Cell label="Libre" value={r.disk ? fmtBytes((r.disk as any).free) : '—'} />
        </Grid>
      </Card>

      <Card icon="time-outline" label="Tiempo activo">
        <Text style={styles.valueText}>
          {typeof r.uptime === 'number' ? fmtUptime(r.uptime) : '—'}
        </Text>
      </Card>
    </ScreenChrome>
  );
}

function fmtUptime(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${h}h ${m}m`;
}

function Card({ icon, label, children }: { icon: string; label: string; children: React.ReactNode }) {
  const { THEME } = useTheme();
  const styles = useStyles(makeStyles);
  return (
    <GlassCard>
      <View style={styles.cardHead}>
        <Ionicons name={icon as keyof typeof Ionicons.glyphMap} size={16} color={THEME.secondary} />
        <Text style={styles.cardLabel}>{label}</Text>
      </View>
      {children}
    </GlassCard>
  );
}

function Grid({ children }: { children: React.ReactNode }) {
  const styles = useStyles(makeStyles);
  return <View style={styles.grid}>{children}</View>;
}

function Cell({ label, value }: { label: string; value: string }) {
  const styles = useStyles(makeStyles);
  return (
    <View style={styles.cell}>
      <Text style={styles.cellLabel}>{label}</Text>
      <Text style={styles.valueText}>{value}</Text>
    </View>
  );
}

const makeStyles = ({ THEME }: Palette) =>
  StyleSheet.create({
    actions: {
      flexDirection: 'row',
      justifyContent: 'flex-end',
      marginBottom: 8,
    },
    refreshBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
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
    hostLine: {
      color: THEME.secondary,
      fontSize: 12,
      textAlign: 'center',
      marginBottom: 12,
    },
    cardHead: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
      marginBottom: 12,
    },
    cardLabel: {
      color: THEME.label,
      fontSize: 13,
      fontWeight: '600',
    },
    grid: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 12,
    },
    cell: {
      flexBasis: '46%',
      gap: 2,
    },
    cellLabel: {
      color: THEME.tertiary,
      fontSize: 11,
    },
    valueText: {
      color: THEME.label,
      fontSize: 16,
      fontWeight: '600',
    },
  });
