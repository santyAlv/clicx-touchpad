import AsyncStorage from '@react-native-async-storage/async-storage';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { alpha, parseHex, rgbToHsv, shadeOf, toHex } from './color';

/**
 * Runtime palette derived from the host's accent.
 *
 * The host picks a colour in Opciones, stores it in deck.json and pushes it to
 * the phone inside every `hello` / `deckSync`. It derives its own whole palette
 * from that colour by shading it in HSV (see receiver/host_ui/lib/theme.dart);
 * this is the same idea on the phone, so the two stay in step.
 *
 * The static `THEME` / `DOKKE_GLASS` exports elsewhere are this palette at the
 * default accent. Components read the live one through [useTheme].
 */

export const DEFAULT_ACCENT = '#9CB080';

const STORAGE_KEY = 'clicx.accent.v1';

// --- the palette ------------------------------------------------------------

export type Palette = ReturnType<typeof makePalette>;
export type Theme = Palette['THEME'];
export type Glass = Palette['DOKKE_GLASS'];

export function makePalette(accentHex: string) {
  const rgb = parseHex(accentHex) ?? parseHex(DEFAULT_ACCENT)!;
  const accent = toHex(rgb);
  const hsv = rgbToHsv(rgb);

  /**
   * A shade of the accent at a fixed saturation/value, the way the host builds
   * its surfaces. A greyscale accent has no meaningful hue, so its shades stay
   * grey instead of drifting to red.
   */
  const shade = (s: number, v: number): string => shadeOf(hsv, s, v);

  // The saturation/value pairs are the ones the original forest-moss palette
  // used, measured off its hexes, so accent = #9CB080 reproduces that look.
  const canvas = shade(0.29, 0.22); // was #273338
  const deep = shade(0.31, 0.16); // was #1C2629
  const page = shade(0.5, 0.34); // was #2B5748
  const pageMid = shade(0.49, 0.3); // was #274C40
  const pageTop = shade(0.28, 0.53); // was #618764
  const ink = '#FFFFFF';

  // Status colours never follow the accent: red has to keep meaning "stop".
  const red = '#C45C4A';

  const THEME = {
    canvas,
    canvasRaised: page,
    // The trackpad is the one black surface: its dots and touch ring are what
    // carry the accent, and they need an unlit field to read against.
    padSurface: '#000000',
    // Glass, not paint: every screen sits on the DokkeBackdrop, so a surface is
    // a translucent pane over that wash. surface2 is the raised/pressed step.
    surface: alpha(accent, 0.1),
    surface2: alpha(accent, 0.24),
    tile: alpha(page, 0.86),
    tileBorder: alpha(accent, 0.42),
    tileHighlight: alpha(accent, 0.18),
    glass: alpha(accent, 0.12),
    hairline: alpha(accent, 0.28),
    // Every piece of text is the same opaque white. Tinting it with the accent
    // and fading it out looked soft, but on a surface that is itself a shade of
    // that accent the faint steps stopped separating from the background —
    // hierarchy comes from size and weight instead.
    label: ink,
    secondary: ink,
    tertiary: ink,
    // For decoration that must stay quiet: idle dots, spent bars. Never text.
    dim: 'rgba(255, 255, 255, 0.22)',
    orange: accent,
    orangeDeep: pageTop,
    orangeSoft: accent,
    blue: pageTop,
    blueBright: accent,
    green: accent,
    red,
    purple: pageTop,
    teal: accent,
    indigo: page,
    pink: accent,
    yellow: accent,
    gray: pageTop,
  } as const;

  const DOKKE_GLASS = {
    canvas,
    page,
    pageMid,
    pageTop,
    ink,
    ink2: ink,
    ink3: ink,
    inkDim: 'rgba(255, 255, 255, 0.22)',
    accent: pageTop,
    amber: accent,
    amberDeep: pageTop,
    green: accent,
    red,
    glass: alpha(accent, 0.1),
    edge: alpha(accent, 0.22),
    tileR: 0.29,
    tileIn: 0.84,
    tileInR: 0.19,
    wellBorder: alpha(accent, 0.4),
    wellGlow: alpha(pageTop, 0.28),
    emptyFill: alpha(canvas, 0.55),
    emptyBorder: alpha(accent, 0.22),
    plate: accent,
  } as const;

  const DOKKE_BG = {
    top: alpha(accent, 0.28),
    side: alpha(pageTop, 0.22),
    line: [page, canvas, deep] as const,
  };

  const AGLASS_FILL = [
    alpha(accent, 0.28),
    alpha(pageTop, 0.2),
    alpha(canvas, 0.78),
  ] as const;

  const AGLASS_SHEEN = [alpha(ink, 0.22), 'transparent'] as const;

  const DOCK_CARD = {
    fill: alpha(page, 0.55),
    wash: alpha(canvas, 0.32),
    stroke: alpha(accent, 0.22),
    radius: 28,
  } as const;

  return {
    accent,
    THEME,
    DOKKE_GLASS,
    DOKKE_BG,
    AGLASS_FILL,
    AGLASS_SHEEN,
    DOCK_CARD,
  };
}

export const DEFAULT_PALETTE = makePalette(DEFAULT_ACCENT);

// --- the live accent --------------------------------------------------------

let currentAccent = DEFAULT_ACCENT;
const listeners = new Set<(accent: string) => void>();

/** Normalises to `#RRGGBB`; returns null for anything that is not a hex colour. */
export function normalizeAccent(raw: unknown): string | null {
  if (typeof raw !== 'string') return null;
  const rgb = parseHex(raw);
  return rgb ? toHex(rgb) : null;
}

/**
 * Applies an accent coming from the host. Ignores anything unparseable and
 * no-ops when the colour has not actually changed, so a deck sync every couple
 * of seconds does not re-render the tree.
 */
export function setAccent(raw: unknown, { persist = true } = {}): void {
  const next = normalizeAccent(raw);
  if (!next || next === currentAccent) return;
  currentAccent = next;
  if (persist) {
    void AsyncStorage.setItem(STORAGE_KEY, next).catch(() => {});
  }
  for (const listener of listeners) listener(next);
}

export function getAccent(): string {
  return currentAccent;
}

/** Last accent the host sent, so the app opens in the right colour. */
export async function loadStoredAccent(): Promise<void> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    setAccent(raw, { persist: false });
  } catch {
    // a missing or unreadable store just means the default accent
  }
}

// --- hooks ------------------------------------------------------------------

/**
 * The live palette. Returns the same field names the static modules export, so
 * a component can destructure `{ THEME }` and leave its markup untouched.
 */
export function useTheme(): Palette {
  const [accent, setLocal] = useState(currentAccent);

  useEffect(() => {
    // Catch an accent that arrived between render and subscribe.
    setLocal(currentAccent);
    listeners.add(setLocal);
    return () => {
      listeners.delete(setLocal);
    };
  }, []);

  return useMemo(() => makePalette(accent), [accent]);
}

/**
 * Builds a StyleSheet from the live palette, rebuilt only when the accent
 * changes. `factory` must be module-level so it stays referentially stable.
 */
export function useStyles<T>(factory: (palette: Palette) => T): T {
  const palette = useTheme();
  const build = useCallback(() => factory(palette), [factory, palette]);
  return useMemo(build, [build]);
}
