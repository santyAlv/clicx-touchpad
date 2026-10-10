import { Ionicons } from '@expo/vector-icons';
// expo-clipboard has no default export; a default import binds undefined and
// every Clipboard.setStringAsync call throws before the host is ever told.
import * as Clipboard from 'expo-clipboard';
import { useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Switch, Text, TextInput, View } from 'react-native';
import type { ClicxMessage } from './protocol';
import { GlassCard, ScreenChrome } from './screenChrome';
import { THEME } from './theme';
import { type Palette, useStyles, useTheme } from './palette';

type Props = {
  send: (msg: ClicxMessage) => void;
  onReply: (cb: (data: Record<string, unknown>) => void) => () => void;
  onBack: () => void;
};

type HistItem = { ts: number; len: number; text: string };

/** Centro de control → Portapapeles. Copiar/pegar entre PC y teléfono. */
export function ClipboardScreen({ send, onReply, onBack }: Props) {
  const { THEME } = useTheme();
  const styles = useStyles(makeStyles);
  const [items, setItems] = useState<HistItem[]>([]);
  const [auto, setAuto] = useState(false);
  const [draft, setDraft] = useState('');
  const [statusMsg, setStatusMsg] = useState('');
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const stop = onReply((data) => {
      if (data?.t === 'clipboard' && data?.action === 'history' && Array.isArray(data.items)) {
        setItems(data.items as HistItem[]);
      }
      if (data?.t === 'clipboard' && data?.action === 'push' && typeof data.text === 'string') {
        const text = data.text as string;
        setItems((prev) => {
          const next = [{ ts: Number(data.ts ?? 0), len: text.length, text } as HistItem].concat(prev).slice(0, 20);
          return next;
        });
      }
    });
    return stop;
  }, [onReply]);

  // Refresh history periodically until auto-sync pushes take over.
  useEffect(() => {
    send({ t: 'clipboard', action: 'history' });
    timer.current = setInterval(() => send({ t: 'clipboard', action: 'history' }), 2500);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [send]);

  // Cleanup: disable auto-sync when leaving the screen.
  useEffect(() => {
    return () => {
      try {
        send({ t: 'clipboard', action: 'sync', on: false });
      } catch {
        // ignore
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const sendToPc = async () => {
    const text = draft.trim();
    if (!text) return;
    Clipboard.setStringAsync(text);
    send({ t: 'clipboard', action: 'set', text });
    setDraft('');
    flash('Enviado a la PC');
  };

  const copyFromPc = async () => {
    send({ t: 'clipboard', action: 'push_back' });
  };

  const copyItem = async (text: string) => {
    await Clipboard.setStringAsync(text);
    flash('Copiado en el teléfono');
  };

  const toggleAuto = (on: boolean) => {
    setAuto(on);
    send({ t: 'clipboard', action: 'sync', on });
    flash(on ? 'Sincronización ON' : 'Sincronización OFF');
  };

  const clearAll = () => {
    send({ t: 'clipboard', action: 'clear' });
    setItems([]);
    flash('Historial borrado');
  };

  const flash = (msg: string) => {
    setStatusMsg(msg);
    setTimeout(() => setStatusMsg(''), 1600);
  };

  return (
    <ScreenChrome title="Portapapeles" subtitle="Clipboard compartido (OFF por defecto)" onBack={onBack}>
      <GlassCard>
        <Text style={styles.cardLabel}>Texto a copiar en la PC</Text>
        <TextInput
          style={styles.input}
          value={draft}
          onChangeText={setDraft}
          placeholder="Escribí o pegá texto aquí…"
          placeholderTextColor={THEME.tertiary}
          multiline
        />
        <View style={styles.row}>
          <Btn label="Enviar a PC" icon="arrow-forward-circle" onPress={sendToPc} primary />
          <Btn label="Traer de PC" icon="clipboard" onPress={copyFromPc} />
        </View>
      </GlassCard>

      <GlassCard>
        <View style={styles.syncRow}>
          <View style={styles.syncInfo}>
            <Text style={styles.cardLabel}>Sincronización automática</Text>
            <Text style={styles.syncHint}>Envía al teléfono lo que copies en la PC</Text>
          </View>
          <Switch value={auto} onValueChange={toggleAuto} trackColor={{ true: THEME.orangeDeep }} thumbColor={THEME.label} />
        </View>
      </GlassCard>

      <View style={styles.histHead}>
        <Text style={styles.cardLabel}>Historial</Text>
        <Pressable onPress={clearAll} hitSlop={8}>
          <Text style={styles.clearBtn}>Borrar</Text>
        </Pressable>
      </View>

      {items.length === 0 ? (
        <Text style={styles.empty}>Sin entradas aún.</Text>
      ) : (
        items.map((it, i) => (
          <Pressable key={String(it.ts) + i} style={styles.histItem} onPress={() => copyItem(it.text)}>
            <Text style={styles.histText} numberOfLines={2}>
              {it.text}
            </Text>
            <Text style={styles.histMeta}>{it.len} caracteres • tocá para copiar</Text>
          </Pressable>
        ))
      )}

      {statusMsg ? <Text style={styles.status}>{statusMsg}</Text> : null}
    </ScreenChrome>
  );
}

function Btn({
  label,
  icon,
  onPress,
  primary,
}: {
  label: string;
  icon: string;
  onPress: () => void;
  primary?: boolean;
}) {
  const { THEME } = useTheme();
  const styles = useStyles(makeStyles);
  return (
    <Pressable style={[styles.btn, primary && styles.btnPrimary]} onPress={onPress}>
      <Ionicons name={icon as keyof typeof Ionicons.glyphMap} size={18} color={THEME.label} />
      <Text style={styles.btnLabel}>{label}</Text>
    </Pressable>
  );
}

const makeStyles = ({ THEME }: Palette) =>
  StyleSheet.create({
    cardLabel: {
      color: THEME.label,
      fontSize: 13,
      fontWeight: '600',
      marginBottom: 8,
    },
    input: {
      backgroundColor: THEME.canvas,
      borderRadius: 10,
      color: THEME.label,
      minHeight: 64,
      padding: 10,
      textAlignVertical: 'top',
      marginBottom: 10,
    },
    row: {
      flexDirection: 'row',
      gap: 10,
    },
    btn: {
      flex: 1,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 6,
      backgroundColor: THEME.surface2,
      borderRadius: 10,
      paddingVertical: 12,
    },
    btnPrimary: {
      backgroundColor: THEME.orangeDeep,
    },
    btnLabel: {
      color: THEME.label,
      fontSize: 13,
      fontWeight: '600',
    },
    syncRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
    },
    syncInfo: {
      flex: 1,
      marginRight: 12,
    },
    syncHint: {
      color: THEME.secondary,
      fontSize: 11,
    },
    histHead: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginTop: 4,
    },
    clearBtn: {
      color: THEME.red,
      fontSize: 12,
      fontWeight: '600',
    },
    empty: {
      color: THEME.tertiary,
      fontSize: 13,
      textAlign: 'center',
      marginTop: 16,
    },
    histItem: {
      backgroundColor: THEME.surface,
      borderRadius: 12,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: THEME.hairline,
      padding: 12,
      marginBottom: 8,
    },
    histText: {
      color: THEME.label,
      fontSize: 13,
    },
    histMeta: {
      color: THEME.tertiary,
      fontSize: 10,
      marginTop: 4,
    },
    status: {
      color: THEME.orange,
      fontSize: 12,
      textAlign: 'center',
      marginTop: 8,
      fontWeight: '600',
    },
  });
