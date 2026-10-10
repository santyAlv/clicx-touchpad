import { Ionicons } from '@expo/vector-icons';
import { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { ClicxMessage } from './protocol';
import { type Palette, useStyles, useTheme } from './palette';
import { GlassCard, ScreenChrome } from './screenChrome';

type Props = {
  send: (msg: ClicxMessage) => void;
  onReply: (cb: (data: Record<string, unknown>) => void) => () => void;
  onBack: () => void;
};

type Tokens = {
  input?: number;
  output?: number;
  cacheRead?: number;
  cacheWrite?: number;
};
type Week = {
  tokens?: Tokens;
  billable?: number;
  messages?: number;
  byDay?: { day: string; tokens: number }[];
  cap?: number | null;
  percent?: number | null;
};
type Context = {
  model?: string;
  tokens?: number;
  window?: number;
  percent?: number | null;
} | null;
type Session = {
  startedAt: number;
  resetsAt: number;
  messages: number;
  tokens: number;
  cap?: number | null;
  percent?: number | null;
} | null;
type Limits = {
  plan?: string | null;
  usedPercent?: number;
  windowMinutes?: number;
  resetsAt?: number;
  seenAt?: number;
} | null;
type Usage = {
  claude?: {
    week?: Week;
    session?: Session;
    context?: Context;
    models?: { model: string; tokens: number }[];
    limits?: { sessionTokens?: number; weekTokens?: number };
  };
  codex?: { week?: Week; limits?: Limits };
} | null;

const POLL_MS = 15000;

function compact(n: unknown): string {
  if (typeof n !== 'number' || !Number.isFinite(n)) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}k`;
  return `${n}`;
}

/** "hace 3 días" / "hace 2 h" since an epoch-seconds instant. */
function since(epoch: unknown): string {
  if (typeof epoch !== 'number' || !Number.isFinite(epoch)) return '—';
  const mins = Math.max(0, Math.round((Date.now() - epoch * 1000) / 60000));
  if (mins < 60) return `hace ${mins} m`;
  const h = Math.floor(mins / 60);
  if (h < 48) return `hace ${h} h`;
  return `hace ${Math.floor(h / 24)} días`;
}

/** "2 h 14 m" until an epoch-seconds instant, or "—" once it has passed. */
function until(epoch: unknown): string {
  if (typeof epoch !== 'number' || !Number.isFinite(epoch)) return '—';
  const left = epoch * 1000 - Date.now();
  if (left <= 0) return 'ya';
  const mins = Math.round(left / 60000);
  const h = Math.floor(mins / 60);
  return h > 0 ? `${h} h ${mins % 60} m` : `${mins} m`;
}

/** Centro de control → uso semanal de Claude y Codex, leído del host. */
export function UsageScreen({ send, onReply, onBack }: Props) {
  const { THEME } = useTheme();
  const styles = useStyles(makeStyles);
  const [usage, setUsage] = useState<Usage>(null);
  const [refreshing, setRefreshing] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const stop = onReply((data) => {
      if (data?.t === 'usage') setUsage(data as Usage);
    });
    return stop;
  }, [onReply]);

  useEffect(() => {
    send({ t: 'usage' });
    timer.current = setInterval(() => send({ t: 'usage' }), POLL_MS);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [send]);

  const refresh = () => {
    setRefreshing(true);
    send({ t: 'usage' });
    setTimeout(() => setRefreshing(false), 400);
  };

  const claude = usage?.claude;
  const codex = usage?.codex;
  const session = claude?.session ?? null;
  const limits = codex?.limits ?? null;
  const context = claude?.context ?? null;
  const caps = claude?.limits ?? {};
  const days = claude?.week?.byDay ?? [];
  // A snapshot whose own window already closed says nothing about right now.
  const codexStale =
    !!limits &&
    typeof limits.resetsAt === 'number' &&
    limits.resetsAt * 1000 < Date.now();
  const peak = Math.max(1, ...days.map((d) => d.tokens));

  return (
    <ScreenChrome title="Uso de Claude y Codex" subtitle="Semana y ventana de 5 h" onBack={onBack}>
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

      <GlassCard>
        <Text style={styles.cardLabel}>Claude · límites</Text>
        {context ? (
          <Meter
            label="Ventana de contexto"
            note={`${compact(context.tokens)} / ${compact(context.window)}`}
            percent={context.percent ?? null}
          />
        ) : null}
        <Meter
          label="Límite de 5 horas"
          note={session ? `Se restablece en ${until(session.resetsAt)}` : 'Sin ventana abierta'}
          percent={session?.percent ?? null}
          fallback={session ? `${compact(session.tokens)} usados` : undefined}
        />
        <Meter
          label="Semanal · últimos 7 días"
          note="Móvil, 7 días"
          percent={claude?.week?.percent ?? null}
          fallback={`${compact(claude?.week?.billable)} usados`}
        />
        <CapEditor
          sessionCap={caps.sessionTokens}
          weekCap={caps.weekTokens}
          onSet={(next) => send({ t: 'usage', action: 'limits', ...next })}
        />
      </GlassCard>

      <GlassCard>
        <Text style={styles.cardLabel}>Claude · ventana de 5 h</Text>
        {session ? (
          <>
            <View style={styles.grid}>
              <Cell label="Se reinicia en" value={until(session.resetsAt)} />
              <Cell label="Tokens" value={compact(session.tokens)} />
              <Cell label="Mensajes" value={`${session.messages}`} />
            </View>
            <Text style={styles.hint}>
              La ventana abre con el primer mensaje y dura 5 h.
            </Text>
          </>
        ) : (
          <Text style={styles.empty}>Sin ventana abierta.</Text>
        )}
      </GlassCard>

      <GlassCard>
        <Text style={styles.cardLabel}>Claude · últimos 7 días</Text>
        <View style={styles.grid}>
          <Cell label="Tokens" value={compact(claude?.week?.billable)} />
          <Cell label="Mensajes" value={compact(claude?.week?.messages)} />
          <Cell label="Caché leído" value={compact(claude?.week?.tokens?.cacheRead)} />
        </View>
        <View style={styles.bars}>
          {days.map((d) => (
            <View key={d.day} style={styles.barSlot}>
              <View
                style={[
                  styles.bar,
                  { height: Math.max(3, (d.tokens / peak) * 64) },
                ]}
              />
              <Text style={styles.barDay}>{d.day.slice(8)}</Text>
            </View>
          ))}
        </View>
        {(claude?.models ?? []).map((m) => (
          <View key={m.model} style={styles.row}>
            <Text style={styles.rowLabel} numberOfLines={1}>
              {m.model}
            </Text>
            <Text style={styles.rowValue}>{compact(m.tokens)}</Text>
          </View>
        ))}
      </GlassCard>

      <GlassCard>
        <Text style={styles.cardLabel}>Codex</Text>
        {limits ? (
          <>
            <View style={styles.grid}>
              <Cell
                label="Límite usado"
                value={
                  typeof limits.usedPercent === 'number'
                    ? `${limits.usedPercent.toFixed(1)}%`
                    : '—'
                }
              />
              <Cell
                label={codexStale ? 'Medido' : 'Se reinicia en'}
                value={codexStale ? since(limits.seenAt) : until(limits.resetsAt)}
              />
              <Cell label="Plan" value={limits.plan ? String(limits.plan) : '—'} />
            </View>
            <View style={styles.track}>
              <View
                style={[
                  styles.fill,
                  {
                    width: `${Math.min(100, Math.max(0, limits.usedPercent ?? 0))}%`,
                  },
                  codexStale && styles.fillStale,
                ]}
              />
            </View>
            <Text style={styles.hint}>
              {codexStale
                ? 'Esta lectura es de una sesión vieja: su ventana ya cerró, así que no dice nada del uso de ahora. Abrí Codex para que registre una nueva.'
                : 'Codex guarda su propio porcentaje; Claude no publica el tope, por eso arriba van tokens y no un porcentaje.'}
            </Text>
          </>
        ) : (
          <Text style={styles.empty}>Sin datos de Codex todavía.</Text>
        )}
      </GlassCard>
    </ScreenChrome>
  );
}

/**
 * One labelled bar. A percentage needs a cap to measure against; without one it
 * shows what was spent and an empty track rather than a made-up fraction.
 */
function Meter({
  label,
  note,
  percent,
  fallback,
}: {
  label: string;
  note: string;
  percent: number | null;
  fallback?: string;
}) {
  const { THEME } = useTheme();
  const styles = useStyles(makeStyles);
  const known = typeof percent === 'number';
  const hot = known && percent >= 85;
  return (
    <View style={styles.meter}>
      <View style={styles.meterHead}>
        <Text style={styles.meterLabel} numberOfLines={1}>
          {label}
        </Text>
        <Text style={styles.meterNote} numberOfLines={1}>
          {note}
        </Text>
        <Text style={styles.meterValue}>
          {known ? `${Math.round(percent)}%` : (fallback ?? '—')}
        </Text>
      </View>
      <View style={styles.track}>
        <View
          style={[
            styles.fill,
            { width: `${known ? Math.min(100, Math.max(0, percent)) : 0}%` },
            hot && { backgroundColor: THEME.red },
          ]}
        />
      </View>
    </View>
  );
}

/** Steppers for the two caps the percentages are measured against. */
function CapEditor({
  sessionCap,
  weekCap,
  onSet,
}: {
  sessionCap?: number;
  weekCap?: number;
  onSet: (next: { sessionTokens?: number; weekTokens?: number }) => void;
}) {
  const styles = useStyles(makeStyles);
  const rows: {
    key: 'sessionTokens' | 'weekTokens';
    label: string;
    value: number;
    step: number;
  }[] = [
    { key: 'sessionTokens', label: 'Tope de 5 h', value: sessionCap ?? 0, step: 500_000 },
    { key: 'weekTokens', label: 'Tope semanal', value: weekCap ?? 0, step: 5_000_000 },
  ];
  return (
    <View style={styles.caps}>
      <Text style={styles.hint}>
        Claude lee sus porcentajes en vivo y no los guarda, así que las dos barras
        de arriba necesitan que le digas el tope de tu plan.
      </Text>
      {rows.map((r) => (
        <View key={r.key} style={styles.capRow}>
          <Text style={styles.rowLabel}>{r.label}</Text>
          <Pressable
            style={styles.capBtn}
            onPress={() => onSet({ [r.key]: Math.max(0, r.value - r.step) })}
          >
            <Text style={styles.capBtnText}>−</Text>
          </Pressable>
          <Text style={styles.capValue}>{r.value ? compact(r.value) : 'sin tope'}</Text>
          <Pressable
            style={styles.capBtn}
            onPress={() => onSet({ [r.key]: r.value + r.step })}
          >
            <Text style={styles.capBtnText}>+</Text>
          </Pressable>
        </View>
      ))}
    </View>
  );
}

function Cell({ label, value }: { label: string; value: string }) {
  const styles = useStyles(makeStyles);
  return (
    <View style={styles.cell}>
      <Text style={styles.cellLabel}>{label}</Text>
      <Text style={styles.cellValue}>{value}</Text>
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
      backgroundColor: THEME.surface,
      borderRadius: 10,
      paddingHorizontal: 12,
      paddingVertical: 8,
    },
    refreshText: {
      color: THEME.label,
      fontSize: 12,
      fontWeight: '600',
    },
    cardLabel: {
      color: THEME.label,
      fontSize: 13,
      fontWeight: '600',
      marginBottom: 12,
    },
    grid: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 12,
    },
    cell: {
      flexGrow: 1,
      minWidth: '28%',
    },
    cellLabel: {
      color: THEME.secondary,
      fontSize: 11,
    },
    cellValue: {
      color: THEME.label,
      fontSize: 17,
      fontWeight: '700',
      marginTop: 2,
    },
    // Seven columns, each scaled against the busiest day of the week.
    bars: {
      flexDirection: 'row',
      alignItems: 'flex-end',
      justifyContent: 'space-between',
      height: 84,
      marginTop: 16,
    },
    barSlot: {
      alignItems: 'center',
      flex: 1,
    },
    bar: {
      width: 14,
      borderRadius: 4,
      backgroundColor: THEME.orange,
    },
    barDay: {
      color: THEME.tertiary,
      fontSize: 10,
      marginTop: 6,
    },
    row: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginTop: 10,
    },
    rowLabel: {
      color: THEME.secondary,
      fontSize: 12,
      flex: 1,
    },
    rowValue: {
      color: THEME.label,
      fontSize: 12,
      fontWeight: '600',
    },
    meter: {
      marginBottom: 16,
    },
    meterHead: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 8,
      marginBottom: 8,
    },
    meterLabel: {
      color: THEME.label,
      fontSize: 13,
      fontWeight: '600',
    },
    meterNote: {
      color: THEME.secondary,
      fontSize: 11,
      flex: 1,
      textAlign: 'right',
    },
    meterValue: {
      color: THEME.label,
      fontSize: 13,
      fontWeight: '700',
    },
    caps: {
      marginTop: 4,
    },
    capRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 10,
      marginTop: 10,
    },
    capBtn: {
      width: 34,
      height: 34,
      borderRadius: 10,
      backgroundColor: THEME.surface2,
      alignItems: 'center',
      justifyContent: 'center',
    },
    capBtnText: {
      color: THEME.label,
      fontSize: 17,
      fontWeight: '700',
    },
    capValue: {
      color: THEME.label,
      fontSize: 13,
      fontWeight: '600',
      minWidth: 68,
      textAlign: 'center',
    },
    track: {
      height: 8,
      borderRadius: 4,
      backgroundColor: THEME.surface2,
      marginTop: 14,
      overflow: 'hidden',
    },
    fill: {
      height: 8,
      borderRadius: 4,
      backgroundColor: THEME.orange,
    },
    fillStale: {
      backgroundColor: THEME.dim,
    },
    hint: {
      color: THEME.tertiary,
      fontSize: 11,
      lineHeight: 15,
      marginTop: 12,
    },
    empty: {
      color: THEME.secondary,
      fontSize: 13,
    },
  });
