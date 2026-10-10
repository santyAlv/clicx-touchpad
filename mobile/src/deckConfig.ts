import AsyncStorage from '@react-native-async-storage/async-storage';
import { DOKKE, IOS } from './theme';

export { DOKKE, IOS, THEME } from './theme';

const PAGE_KEY = 'clicx.deck.page.v1';
const MODE_KEY = 'clicx.surface.mode.v1';

export type DeckAction =
  | { kind: 'hotkey'; keys: string[] }
  | { kind: 'volume'; action: 'mute' | 'up' | 'down' }
  | { kind: 'shell'; command?: string; cwd?: string; app?: string }
  | { kind: 'app'; app?: string };

export type DeckButton = {
  id: string;
  label: string;
  hint?: string;
  /** SF Symbol–style Ionicons name */
  icon: string;
  /** PNG base64 from host (Windows app icon) */
  iconB64?: string;
  color: string;
  action: DeckAction;
};

export type DeckPage = {
  id: string;
  title: string;
  buttons: DeckButton[];
};

export type HostDeck = {
  version?: number;
  pages: DeckPage[];
};

export function parseHostDeck(raw: unknown): HostDeck | null {
  if (!raw || typeof raw !== 'object') return null;
  const deck = raw as { pages?: unknown; version?: unknown };
  if (!Array.isArray(deck.pages)) return null;
  const pages: DeckPage[] = [];
  for (const p of deck.pages) {
    if (!p || typeof p !== 'object') continue;
    const page = p as Record<string, unknown>;
    const buttons: DeckButton[] = [];
    const rawButtons = page.buttons;
    if (Array.isArray(rawButtons)) {
      for (const b of rawButtons) {
        if (!b || typeof b !== 'object') continue;
        const btn = b as Record<string, unknown>;
        const action = btn.action;
        if (!action || typeof action !== 'object') continue;
        const act = action as Record<string, unknown>;
        const kind = act.kind;
        if (kind !== 'hotkey' && kind !== 'volume' && kind !== 'shell' && kind !== 'app') continue;
        let parsed: DeckAction;
        if (kind === 'hotkey') {
          const keys = act.keys;
          if (!Array.isArray(keys)) continue;
          parsed = { kind: 'hotkey', keys: keys.map(String) };
        } else if (kind === 'volume') {
          const v = String(act.action ?? 'mute');
          if (v !== 'mute' && v !== 'up' && v !== 'down') continue;
          parsed = { kind: 'volume', action: v };
        } else if (kind === 'app') {
          parsed = {
            kind: 'app',
            app: String(act.app ?? ''),
          };
        } else {
          parsed = {
            kind: 'shell',
            command: String(act.command ?? ''),
            cwd: String(act.cwd ?? ''),
            ...(act.app ? { app: String(act.app) } : {}),
          };
        }
        const iconB64 =
          typeof btn.iconB64 === 'string' && btn.iconB64.length > 0
            ? btn.iconB64
            : undefined;
        buttons.push({
          id: String(btn.id ?? ''),
          label: String(btn.label ?? 'Btn'),
          icon: String(btn.icon ?? 'ellipse-outline'),
          color: String(btn.color ?? IOS.blue),
          hint: btn.hint ? String(btn.hint) : undefined,
          iconB64,
          action: parsed,
        });
      }
    }
    pages.push({
      id: String(page.id ?? ''),
      title: String(page.title ?? 'Deck'),
      buttons,
    });
  }
  if (!pages.length) return null;
  return { version: Number(deck.version) || 1, pages };
}

export type SurfaceMode = 'trackpad' | 'deck';

export const DECK_COLS_PORTRAIT = 2;
export const DECK_ROWS_PORTRAIT = 4;
export const DECK_COLS_LANDSCAPE = 4;
export const DECK_ROWS_LANDSCAPE = 2;
export const DECK_PAGE_SIZE = 8;

function btn(
  id: string,
  label: string,
  icon: string,
  color: string,
  keys: string[],
  hint?: string,
): DeckButton {
  return {
    id,
    label,
    icon,
    hint,
    color,
    action: { kind: 'hotkey', keys },
  };
}

function vol(
  id: string,
  label: string,
  icon: string,
  color: string,
  action: 'mute' | 'up' | 'down',
): DeckButton {
  return { id, label, icon, color, action: { kind: 'volume', action } };
}

export const DEFAULT_DECK_PAGES: DeckPage[] = [
  {
    id: 'prod',
    title: 'Atajos',
    buttons: [
      btn('copy', 'Copiar', 'copy-outline', IOS.blue, ['ctrl', 'c']),
      btn('paste', 'Pegar', 'clipboard-outline', IOS.green, ['ctrl', 'v']),
      btn('undo', 'Deshacer', 'arrow-undo-outline', IOS.orange, ['ctrl', 'z']),
      btn('save', 'Guardar', 'save-outline', IOS.yellow, ['ctrl', 's']),
      btn('desk', 'Escritorio', 'desktop-outline', IOS.indigo, ['win', 'd']),
      btn('tasks', 'Tareas', 'layers-outline', IOS.purple, ['win', 'tab']),
      btn('search', 'Buscar', 'search-outline', IOS.teal, ['win', 's']),
      btn('shot', 'Captura', 'camera-outline', IOS.pink, ['win', 'shift', 's'], '⇧⌘S'),
      btn('esc', 'Esc', 'close-circle-outline', IOS.red, ['esc']),
      btn('enter', 'Enter', 'return-down-back-outline', IOS.gray, ['enter']),
      btn('space', 'Espacio', 'remove-outline', IOS.gray, ['space']),
      btn('refresh', 'Actualizar', 'refresh-outline', IOS.teal, ['f5']),
    ],
  },
  {
    id: 'media',
    title: 'Media',
    buttons: [
      btn('prev', 'Anterior', 'play-skip-back', IOS.purple, ['left']),
      btn('play', 'Play', 'play', IOS.green, ['space']),
      btn('next', 'Siguiente', 'play-skip-forward', IOS.blue, ['right']),
      vol('vup', 'Subir', 'volume-high-outline', IOS.label, 'up'),
      vol('vmute', 'Silencio', 'volume-mute-outline', IOS.red, 'mute'),
      vol('vdown', 'Bajar', 'volume-low-outline', IOS.orange, 'down'),
      btn('tab', 'Apps', 'apps-outline', IOS.indigo, ['alt', 'tab']),
      btn('close', 'Cerrar', 'close-outline', IOS.red, ['alt', 'f4'], '⌥F4'),
      btn('snap', 'Izquierda', 'chevron-back-outline', IOS.teal, ['win', 'left']),
      btn('snapr', 'Derecha', 'chevron-forward-outline', IOS.teal, ['win', 'right']),
      btn('pgup', 'Arriba', 'chevron-up-outline', IOS.gray, ['pageup']),
      btn('pgdn', 'Abajo', 'chevron-down-outline', IOS.gray, ['pagedown']),
    ],
  },
];

export async function loadDeckPageIndex(): Promise<number> {
  try {
    const raw = await AsyncStorage.getItem(PAGE_KEY);
    if (raw == null) return 0;
    const n = Number(raw);
    return Number.isFinite(n) && n >= 0 ? Math.floor(n) : 0;
  } catch {
    return 0;
  }
}

export async function saveDeckPageIndex(index: number): Promise<void> {
  try {
    await AsyncStorage.setItem(PAGE_KEY, String(index));
  } catch {
    // ignore
  }
}

export async function loadSurfaceMode(): Promise<SurfaceMode> {
  try {
    const raw = await AsyncStorage.getItem(MODE_KEY);
    return raw === 'deck' ? 'deck' : 'trackpad';
  } catch {
    return 'trackpad';
  }
}

export async function saveSurfaceMode(mode: SurfaceMode): Promise<void> {
  try {
    await AsyncStorage.setItem(MODE_KEY, mode);
  } catch {
    // ignore
  }
}
