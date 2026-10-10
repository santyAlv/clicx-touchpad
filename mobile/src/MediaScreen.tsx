import { Ionicons } from '@expo/vector-icons';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { ClicxMessage } from './protocol';
import { ScreenChrome } from './screenChrome';
import { THEME } from './theme';
import { type Palette, useStyles, useTheme } from './palette';

type Props = {
  send: (msg: ClicxMessage) => void;
  onBack: () => void;
};

/** Centro de control → Media. Transport via standard media keys (t:media); the
 *  volumen general uses the existing t:volume domain (no duplication). */
export function MediaScreen({ send, onBack }: Props) {
  const { THEME } = useTheme();
  const styles = useStyles(makeStyles);
  const [muted, setMuted] = useState(false);

  const transport = (action: 'play_pause' | 'prev' | 'next' | 'stop') =>
    send({ t: 'media', action });

  const toggleMute = () => {
    const next = !muted;
    setMuted(next);
    send({ t: 'volume', action: next ? 'mute' : 'unmute' });
  };

  return (
    <ScreenChrome title="Multimedia" subtitle="Teclas estándar de Windows" onBack={onBack}>
      <View style={styles.transportRow}>
        <Round onPress={() => transport('prev')} icon="play-skip-back" />
        <Round onPress={() => transport('play_pause')} icon="play" primary />
        <Round onPress={() => transport('next')} icon="play-skip-forward" />
        <Round onPress={() => transport('stop')} icon="stop" />
      </View>

      <Text style={styles.section}>Volumen general</Text>
      <View style={styles.volumeRow}>
        <Pressable
          style={[styles.volBtn, muted && styles.volBtnActive]}
          onPress={toggleMute}
        >
          <Ionicons
            name={muted ? 'volume-mute-outline' : 'volume-high-outline'}
            size={20}
            color={THEME.label}
          />
          <Text style={styles.volText}>{muted ? 'Silencio' : 'Sonido'}</Text>
        </Pressable>
        <Pressable style={styles.volBtn} onPress={() => send({ t: 'volume', action: 'down' })}>
          <Ionicons name="remove-outline" size={20} color={THEME.label} />
          <Text style={styles.volText}>Bajar</Text>
        </Pressable>
        <Pressable style={styles.volBtn} onPress={() => send({ t: 'volume', action: 'up' })}>
          <Ionicons name="add-outline" size={20} color={THEME.label} />
          <Text style={styles.volText}>Subir</Text>
        </Pressable>
      </View>
    </ScreenChrome>
  );
}

function Round({ onPress, icon, primary }: { onPress: () => void; icon: string; primary?: boolean }) {
  const { THEME } = useTheme();
  const styles = useStyles(makeStyles);
  return (
    <Pressable
      onPress={onPress}
      style={[styles.round, primary && styles.roundPrimary]}
    >
      <Ionicons name={icon as keyof typeof Ionicons.glyphMap} size={30} color="#FFFFFF" />
    </Pressable>
  );
}

const makeStyles = ({ THEME }: Palette) =>
  StyleSheet.create({
    transportRow: {
      flexDirection: 'row',
      justifyContent: 'center',
      alignItems: 'center',
      gap: 14,
      marginVertical: 16,
    },
    round: {
      width: 64,
      height: 64,
      borderRadius: 32,
      backgroundColor: THEME.surface,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: THEME.hairline,
      alignItems: 'center',
      justifyContent: 'center',
    },
    roundPrimary: {
      width: 76,
      height: 76,
      borderRadius: 38,
      // Play/pause is the hero control — solid accent, not glass, so it still
      // reads as primary now that the plain surfaces are translucent.
      backgroundColor: THEME.orangeDeep,
    },
    section: {
      color: THEME.secondary,
      fontSize: 12,
      fontWeight: '600',
      marginTop: 12,
      marginBottom: 8,
    },
    volumeRow: {
      flexDirection: 'row',
      gap: 10,
      flexWrap: 'wrap',
    },
    volBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      paddingHorizontal: 14,
      paddingVertical: 10,
      borderRadius: 12,
      backgroundColor: THEME.surface,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: THEME.hairline,
    },
    volBtnActive: {
      borderColor: THEME.orange,
    },
    volText: {
      color: THEME.label,
      fontSize: 12,
      fontWeight: '600',
    },
  });
