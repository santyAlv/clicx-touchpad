/**
 * Colour maths for the runtime palette. Pure and dependency-free, so it can be
 * compiled and run on its own:
 *
 *   npx tsc src/color.ts --outDir .check --module commonjs --target es2020
 *   node .check/color.js
 */

export type Rgb = { r: number; g: number; b: number };
export type Hsv = { h: number; s: number; v: number };

export function parseHex(hex: string): Rgb | null {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

export function rgbToHsv({ r, g, b }: Rgb): Hsv {
  const rr = r / 255;
  const gg = g / 255;
  const bb = b / 255;
  const max = Math.max(rr, gg, bb);
  const min = Math.min(rr, gg, bb);
  const d = max - min;
  let h = 0;
  if (d !== 0) {
    if (max === rr) h = ((gg - bb) / d) % 6;
    else if (max === gg) h = (bb - rr) / d + 2;
    else h = (rr - gg) / d + 4;
    h *= 60;
    if (h < 0) h += 360;
  }
  return { h, s: max === 0 ? 0 : d / max, v: max };
}

export function hsvToRgb({ h, s, v }: Hsv): Rgb {
  const c = v * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = v - c;
  let rgb: [number, number, number];
  if (h < 60) rgb = [c, x, 0];
  else if (h < 120) rgb = [x, c, 0];
  else if (h < 180) rgb = [0, c, x];
  else if (h < 240) rgb = [0, x, c];
  else if (h < 300) rgb = [x, 0, c];
  else rgb = [c, 0, x];
  return {
    r: Math.round((rgb[0] + m) * 255),
    g: Math.round((rgb[1] + m) * 255),
    b: Math.round((rgb[2] + m) * 255),
  };
}

export function toHex({ r, g, b }: Rgb): string {
  const two = (n: number) => n.toString(16).padStart(2, '0');
  return `#${two(r)}${two(g)}${two(b)}`.toUpperCase();
}

/** `#RRGGBB` at a given alpha, as the `rgba()` string RN styles want. */
export function alpha(hex: string, a: number): string {
  const rgb = parseHex(hex) ?? { r: 0, g: 0, b: 0 };
  return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${a})`;
}

/**
 * A shade of `accent` at a fixed saturation/value — how both the host and the
 * phone build every surface out of the chosen colour. A greyscale accent has no
 * meaningful hue, so its shades stay grey instead of drifting to red.
 */
export function shadeOf(accent: Hsv, s: number, v: number): string {
  return toHex(hsvToRgb({ h: accent.h, s: accent.s < 0.05 ? 0 : s, v }));
}

function selfCheck(): void {
  const eq = (name: string, got: unknown, want: unknown) => {
    const a = JSON.stringify(got);
    const b = JSON.stringify(want);
    if (a !== b) throw new Error(`${name}: got ${a}, want ${b}`);
    console.log(`ok   ${name}`);
  };

  eq('parseHex rejects junk', parseHex('nope'), null);
  eq('parseHex reads a hex', parseHex('#9CB080'), { r: 156, g: 176, b: 128 });

  // Round-tripping must be lossless, or re-tinting would drift on every sync.
  for (const hex of ['#9CB080', '#0A84FF', '#FF9F0A', '#FFFFFF', '#000000']) {
    const back = toHex(hsvToRgb(rgbToHsv(parseHex(hex)!)));
    eq(`round trip ${hex}`, back, hex);
  }

  const moss = rgbToHsv(parseHex('#9CB080')!);
  eq('shade keeps the hue', Math.round(rgbToHsv(parseHex(shadeOf(moss, 0.5, 0.34))!).h), Math.round(moss.h));

  // Grey has no hue to preserve; its shades must stay grey.
  const grey = rgbToHsv(parseHex('#808080')!);
  const shaded = parseHex(shadeOf(grey, 0.5, 0.4))!;
  eq('grey stays grey', shaded.r === shaded.g && shaded.g === shaded.b, true);

  eq('alpha builds rgba', alpha('#9CB080', 0.5), 'rgba(156, 176, 128, 0.5)');
  console.log('\ncolor.ts ok');
}

declare const require: { main?: unknown } | undefined;
declare const module: unknown;
if (typeof require !== 'undefined' && require?.main === module) selfCheck();
