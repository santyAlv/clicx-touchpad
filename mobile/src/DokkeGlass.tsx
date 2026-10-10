import { BlurView } from 'expo-blur';
import { LinearGradient } from 'expo-linear-gradient';
import { type ReactNode } from 'react';
import {
  StyleSheet,
  useWindowDimensions,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import { DOCK_CARD } from './dokkeTokens';
import { type Palette, useStyles, useTheme } from './palette';

/** Forest field + moss wash. */
export function DokkeBackdrop() {
  const { DOKKE_BG } = useTheme();
  const styles = useStyles(makeStyles);
  const { width, height } = useWindowDimensions();
  // True circles sized off the long edge. The originals were wide, short
  // stadiums, and a stadium's straight sides cut a visible line across the
  // screen as soon as the phone turns — a circle has no straight side to show.
  const big = Math.max(width, height) * 1.15;
  const small = big * 0.85;
  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      <LinearGradient
        colors={[...DOKKE_BG.line]}
        locations={[0, 0.55, 1]}
        start={{ x: 0.5, y: 0 }}
        end={{ x: 0.5, y: 1 }}
        style={StyleSheet.absoluteFill}
      />
      <View
        style={[
          styles.bubble,
          {
            width: big,
            height: big,
            borderRadius: big / 2,
            top: -big * 0.52,
            left: -big * 0.12,
            backgroundColor: DOKKE_BG.top,
          },
        ]}
      />
      <View
        style={[
          styles.bubble,
          {
            width: small,
            height: small,
            borderRadius: small / 2,
            top: height * 0.22,
            left: width - small * 0.52,
            backgroundColor: DOKKE_BG.side,
          },
        ]}
      />
    </View>
  );
}

type WellProps = {
  size: number;
  radius: number;
  children?: ReactNode;
  empty?: boolean;
  style?: StyleProp<ViewStyle>;
};

/**
 * Dokke `.aglass` + Mac `glassEffect` fallback.
 * Gradient glass, inset sheen, moss rim.
 */
export function DokkeAglassBox({
  radius,
  children,
  style,
}: {
  radius: number;
  children?: ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  const { DOKKE_GLASS, AGLASS_FILL, AGLASS_SHEEN } = useTheme();
  const styles = useStyles(makeStyles);
  return (
    <View
      style={[
        styles.well,
        { borderRadius: radius, borderColor: DOKKE_GLASS.wellBorder },
        style,
      ]}
    >
      <BlurView
        intensity={36}
        tint="systemChromeMaterialDark"
        experimentalBlurMethod="dimezisBlurView"
        style={[StyleSheet.absoluteFill, { borderRadius: radius }]}
      />
      <LinearGradient
        colors={[...AGLASS_FILL]}
        locations={[0, 0.55, 1]}
        start={{ x: 0.22, y: 0 }}
        end={{ x: 0.78, y: 1 }}
        style={[StyleSheet.absoluteFill, { borderRadius: radius }]}
      />
      <LinearGradient
        colors={[...AGLASS_SHEEN]}
        locations={[0, 0.45]}
        start={{ x: 0.2, y: 0 }}
        end={{ x: 0.7, y: 1 }}
        pointerEvents="none"
        style={[StyleSheet.absoluteFill, { borderRadius: radius }]}
      />
      <View pointerEvents="none" style={[styles.insetRim, { borderRadius: radius }]} />
      {children}
    </View>
  );
}

/** The bright plate a Deck button wears inside its well. */
export function DokkePlate({
  size,
  radius,
  style,
  children,
}: {
  size?: number;
  radius: number;
  style?: StyleProp<ViewStyle>;
  children?: ReactNode;
}) {
  const styles = useStyles(makeStyles);
  return (
    <View
      style={[
        styles.plate,
        { borderRadius: radius },
        size != null ? { width: size, height: size } : null,
        style,
      ]}
    >
      {children}
    </View>
  );
}

export function DokkeAglass({ size, radius, children, empty, style }: WellProps) {
  const { DOKKE_GLASS } = useTheme();
  const styles = useStyles(makeStyles);
  if (empty) {
    return (
      <View
        style={[
          styles.well,
          {
            width: size,
            height: size,
            borderRadius: radius,
            backgroundColor: DOKKE_GLASS.emptyFill,
            borderColor: DOKKE_GLASS.emptyBorder,
          },
          style,
        ]}
      />
    );
  }

  return (
    <DokkeAglassBox radius={radius} style={[{ width: size, height: size }, style]}>
      {children}
    </DokkeAglassBox>
  );
}

/** Mac DockIcon card — white 7% glass + hairline. */
export function DokkeCard({
  children,
  style,
  radius = DOCK_CARD.radius,
}: {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
  radius?: number;
}) {
  const { DOCK_CARD: card } = useTheme();
  const styles = useStyles(makeStyles);
  return (
    <View style={[styles.card, { borderRadius: radius }, style]}>
      <BlurView
        intensity={28}
        tint="systemThinMaterialDark"
        experimentalBlurMethod="dimezisBlurView"
        style={[StyleSheet.absoluteFill, { borderRadius: radius }]}
      />
      <View
        pointerEvents="none"
        style={[StyleSheet.absoluteFill, { borderRadius: radius, backgroundColor: card.fill }]}
      />
      <View
        pointerEvents="none"
        style={[StyleSheet.absoluteFill, { borderRadius: radius, backgroundColor: card.wash }]}
      />
      {children}
    </View>
  );
}

const makeStyles = ({ DOKKE_GLASS, DOKKE_BG, DOCK_CARD }: Palette) =>
  StyleSheet.create({
    bubble: {
      position: 'absolute',
    },
    well: {
      alignItems: 'center',
      justifyContent: 'center',
      overflow: 'hidden',
      borderWidth: 1.5,
    },
    insetRim: {
      ...StyleSheet.absoluteFillObject,
      borderWidth: 1,
      borderColor: 'rgba(255,255,255,0.22)',
      borderBottomColor: 'transparent',
      borderLeftColor: 'transparent',
      borderRightColor: 'transparent',
    },
    plate: {
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: DOKKE_GLASS.plate,
      borderWidth: 1,
      borderColor: 'rgba(255,255,255,0.72)',
    },
    card: {
      overflow: 'hidden',
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: DOCK_CARD.stroke,
      backgroundColor: 'transparent',
    },
  });
