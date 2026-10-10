import { DEFAULT_PALETTE } from './palette';

/**
 * The palette at the default accent.
 *
 * Components should read the live palette with `useTheme()` from ./palette so
 * they re-tint when the host changes the app colour. These static exports are
 * for module-level code that cannot call a hook (deck button defaults, and the
 * fallback values a StyleSheet factory closes over).
 */
export const THEME = DEFAULT_PALETTE.THEME;

/** @deprecated Use THEME — kept so existing imports keep working. */
export const DOKKE = {
  bg: THEME.canvas,
  glow: THEME.canvasRaised,
  accent: THEME.orange,
  accentDeep: THEME.orangeDeep,
  tileBg: THEME.tile,
  tileBorder: THEME.tileBorder,
  tileHighlight: THEME.tileHighlight,
  dot: THEME.tertiary,
  dotActive: THEME.label,
} as const;

/** Accents on the forest canvas. */
export const IOS = {
  bg: THEME.canvas,
  bgElevated: THEME.surface,
  bgTile: THEME.surface2,
  separator: THEME.hairline,
  label: THEME.label,
  secondary: THEME.secondary,
  blue: THEME.blueBright,
  green: THEME.green,
  orange: THEME.orange,
  red: THEME.red,
  purple: THEME.purple,
  teal: THEME.teal,
  indigo: THEME.indigo,
  pink: THEME.pink,
  yellow: THEME.yellow,
  gray: THEME.gray,
} as const;
