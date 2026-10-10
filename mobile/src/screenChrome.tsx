import { Ionicons } from '@expo/vector-icons';
import type { ReactNode } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { DokkeBackdrop, DokkeCard } from './DokkeGlass';
import { DOKKE_GLASS } from './dokkeTokens';
import { THEME } from './theme';
import { type Palette, useStyles, useTheme } from './palette';

type ChromeProps = {
  title: string;
  subtitle?: string;
  onBack: () => void;
  children: ReactNode;
  scroll?: boolean;
};

/** Shared full-screen chrome for Control Center sub-screens (Fase 1). */
export function ScreenChrome({ title, subtitle, onBack, children, scroll = true }: ChromeProps) {
  const { THEME } = useTheme();
  const styles = useStyles(makeStyles);
  return (
    <SafeAreaView style={styles.root} edges={['top', 'left', 'right', 'bottom']}>
      <DokkeBackdrop />
      <View style={styles.header}>
        <Pressable onPress={onBack} hitSlop={12} style={styles.backHit} accessibilityLabel="Volver">
          <Ionicons name="chevron-back" size={24} color={THEME.label} />
        </Pressable>
        <View style={styles.titleWrap}>
          <Text style={styles.title} numberOfLines={1}>
            {title}
          </Text>
          {subtitle ? (
            <Text style={styles.subtitle} numberOfLines={1}>
              {subtitle}
            </Text>
          ) : null}
        </View>
        <View style={styles.backHit} />
      </View>
      {scroll ? (
        <ScrollView
          style={styles.body}
          contentContainerStyle={styles.bodyContent}
          showsVerticalScrollIndicator={false}
        >
          {children}
        </ScrollView>
      ) : (
        <View style={styles.body}>{children}</View>
      )}
    </SafeAreaView>
  );
}

const makeStyles = ({ THEME, DOKKE_GLASS }: Palette) =>
  StyleSheet.create({
    root: {
      flex: 1,
      // The backdrop paints the canvas — same forest wash the Deck sits on.
      backgroundColor: DOKKE_GLASS.canvas,
    },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      paddingHorizontal: 12,
      paddingTop: 4,
      paddingBottom: 10,
    },
    backHit: {
      width: 40,
      height: 40,
      alignItems: 'center',
      justifyContent: 'center',
    },
    titleWrap: {
      flex: 1,
      alignItems: 'center',
    },
    title: {
      color: THEME.label,
      fontSize: 16,
      fontWeight: '600',
      letterSpacing: -0.2,
    },
    subtitle: {
      color: THEME.secondary,
      fontSize: 12,
      marginTop: 1,
    },
    body: {
      flex: 1,
    },
    bodyContent: {
      paddingHorizontal: 16,
      paddingBottom: 32,
    },
  });


/**
 * Section card for the Control Center screens — the Deck's glass, so every
 * screen reads as one surface instead of a flat panel per screen.
 */
export function GlassCard({
  children,
  style,
}: {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <DokkeCard radius={18} style={[cardStyles.card, style]}>
      {children}
    </DokkeCard>
  );
}

const cardStyles = StyleSheet.create({
  card: {
    padding: 16,
    marginBottom: 12,
  },
});
