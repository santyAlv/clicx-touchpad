import { useEffect, useRef, useState } from 'react';
import {
  Pressable,
  StyleSheet,
  Text,
  View,
  type GestureResponderEvent,
  type LayoutChangeEvent,
} from 'react-native';
import { IconVolume, IconVolumeMute } from './Icons';
import { THEME } from './theme';
import { type Palette, useStyles, useTheme } from './palette';

type Props = {
  level: number; // 0–100
  muted: boolean;
  onLevelChange: (level: number) => void;
  onMuteToggle: () => void;
  onClose?: () => void;
};

/**
 * Horizontal volume control — drag the track or tap ± / mute.
 */
export function VolumePill({
  level,
  muted,
  onLevelChange,
  onMuteToggle,
  onClose,
}: Props) {
  const { THEME } = useTheme();
  const styles = useStyles(makeStyles);
  const trackRef = useRef<View>(null);
  const trackLayout = useRef({ x: 0, width: 1 });
  const dragging = useRef(false);
  const [local, setLocal] = useState(level);

  useEffect(() => {
    if (!dragging.current) setLocal(level);
  }, [level]);

  const display = muted && !dragging.current ? 0 : local;
  const fillPct = Math.max(0, Math.min(100, display));

  const onTrackLayout = (e: LayoutChangeEvent) => {
    trackLayout.current.width = Math.max(1, e.nativeEvent.layout.width);
    trackRef.current?.measureInWindow((x) => {
      trackLayout.current.x = x;
    });
  };

  const pageXToLevel = (pageX: number) => {
    const { x, width } = trackLayout.current;
    const t = (pageX - x) / width;
    return Math.round(Math.max(0, Math.min(100, t * 100)));
  };

  const onGrant = (e: GestureResponderEvent) => {
    dragging.current = true;
    trackRef.current?.measureInWindow((x, _y, width) => {
      trackLayout.current = { x, width: Math.max(1, width) };
      const next = pageXToLevel(e.nativeEvent.pageX);
      setLocal(next);
      onLevelChange(next);
    });
  };

  const onMove = (e: GestureResponderEvent) => {
    if (!dragging.current) return;
    const next = pageXToLevel(e.nativeEvent.pageX);
    setLocal(next);
    onLevelChange(next);
  };

  const onRelease = () => {
    dragging.current = false;
  };

  const bump = (delta: number) => {
    const base = muted ? 0 : local;
    const next = Math.max(0, Math.min(100, base + delta));
    setLocal(next);
    onLevelChange(next);
  };

  return (
    <View style={styles.card}>
      <View style={styles.topRow}>
        <Pressable onPress={onMuteToggle} hitSlop={8} style={styles.muteBtn}>
          {muted || display === 0 ? (
            <IconVolumeMute size={20} color={THEME.orange} />
          ) : (
            <IconVolume size={20} color={THEME.orange} />
          )}
        </Pressable>
        <Text style={styles.levelText}>{muted ? 'Mute' : `${fillPct}%`}</Text>
        {onClose ? (
          <Pressable onPress={onClose} hitSlop={8} style={styles.closeBtn}>
            <Text style={styles.closeText}>Listo</Text>
          </Pressable>
        ) : (
          <View style={styles.closeBtn} />
        )}
      </View>

      <View style={styles.sliderRow}>
        <Pressable onPress={() => bump(-5)} hitSlop={10} style={styles.stepBtn}>
          <Text style={styles.stepText}>−</Text>
        </Pressable>

        <View
          ref={trackRef}
          style={styles.track}
          onLayout={onTrackLayout}
          onStartShouldSetResponder={() => true}
          onMoveShouldSetResponder={() => true}
          onResponderTerminationRequest={() => false}
          onResponderGrant={onGrant}
          onResponderMove={onMove}
          onResponderRelease={onRelease}
          onResponderTerminate={onRelease}
        >
          <View style={[styles.fill, { width: `${fillPct}%` }]} />
          <View
            style={[
              styles.thumb,
              { left: `${Math.max(0, Math.min(100, fillPct))}%` },
            ]}
          />
        </View>

        <Pressable onPress={() => bump(5)} hitSlop={10} style={styles.stepBtn}>
          <Text style={styles.stepText}>+</Text>
        </Pressable>
      </View>
    </View>
  );
}

const makeStyles = ({ THEME }: Palette) =>
  StyleSheet.create({
    card: {
      width: '100%',
      maxWidth: 340,
      borderRadius: 18,
      backgroundColor: THEME.surface,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: THEME.hairline,
      paddingHorizontal: 14,
      paddingVertical: 12,
      gap: 12,
    },
    topRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
    },
    muteBtn: {
      width: 36,
      height: 36,
      borderRadius: 18,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: THEME.glass,
    },
    levelText: {
      color: THEME.label,
      fontSize: 15,
      fontWeight: '600',
      fontVariant: ['tabular-nums'],
      letterSpacing: -0.2,
    },
    closeBtn: {
      minWidth: 36,
      height: 36,
      alignItems: 'center',
      justifyContent: 'center',
    },
    closeText: {
      color: THEME.blueBright,
      fontSize: 13,
      fontWeight: '600',
    },
    sliderRow: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 10,
    },
    stepBtn: {
      width: 34,
      height: 34,
      borderRadius: 17,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: THEME.glass,
    },
    stepText: {
      color: THEME.label,
      fontSize: 20,
      fontWeight: '600',
      marginTop: -1,
    },
    track: {
      flex: 1,
      height: 28,
      borderRadius: 14,
      backgroundColor: THEME.glass,
      justifyContent: 'center',
      overflow: 'hidden',
    },
    fill: {
      position: 'absolute',
      left: 0,
      top: 0,
      bottom: 0,
      backgroundColor: THEME.orange,
      borderRadius: 14,
      opacity: 0.92,
    },
    thumb: {
      position: 'absolute',
      width: 18,
      height: 18,
      borderRadius: 9,
      marginLeft: -9,
      backgroundColor: THEME.label,
      borderWidth: 2,
      borderColor: THEME.canvasRaised,
    },
  });
