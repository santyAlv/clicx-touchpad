export type ClicxMessage =
  | { t: 'move'; dx: number; dy: number }
  | { t: 'stop' }
  | { t: 'click'; btn: 'left' | 'right' | 'middle'; n?: number }
  | { t: 'down'; btn: 'left' | 'right' | 'middle' }
  | { t: 'up'; btn: 'left' | 'right' | 'middle' }
  | { t: 'scroll'; dx: number; dy: number }
  | { t: 'zoom'; factor: number }
  | { t: 'gesture'; name: string }
  | { t: 'hotkey'; keys: string[] }
  | { t: 'type'; text: string }
  | { t: 'key'; name: string }
  | {
      t: 'volume';
      action: 'set' | 'mute' | 'unmute' | 'toggle' | 'up' | 'down';
      level?: number;
    }
  | { t: 'laser'; on: boolean; color?: string; size?: number }
  | { t: 'deck'; id: string }
  | { t: 'status'; get: boolean }
  | { t: 'action'; name: string; confirm?: 'prepare' | 'go' }
  | { t: 'media'; action: 'play_pause' | 'prev' | 'next' | 'stop' }
  | {
      t: 'app_volume';
      action: 'list' | 'set' | 'mute';
      id?: number;
      volume?: number;
      muted?: boolean;
    }
  | {
      t: 'windows';
      action:
        | 'list'
        | 'focus'
        | 'minimize'
        | 'maximize'
        | 'restore'
        | 'close'
        | 'foreground';
      id?: number;
      force?: boolean;
    }
  | { t: 'usage'; action?: 'limits'; sessionTokens?: number; weekTokens?: number }
  | {
      t: 'clipboard';
      action: 'set' | 'push_back' | 'history' | 'clear' | 'sync';
      text?: string;
      on?: boolean;
    }
  | {
      t: 'file';
      action:
        | 'meta'
        | 'chunk'
        | 'done'
        | 'cancel'
        | 'list'
        | 'download'
        | 'pull';
      id?: string;
      name?: string;
      size?: number;
      offset?: number;
      folder?: 'from_phone' | 'from_pc';
    };

export const DEFAULT_PORT = 51234;
export const CONNECT_TIMEOUT_MS = 12000;

/** Strip schemes and trailing slashes from user-entered host. */
export function normalizeHostInput(host: string): string {
  let h = host.trim();
  h = h.replace(/^wss?:\/\//i, '');
  h = h.replace(/^https?:\/\//i, '');
  return h.replace(/\/+$/, '');
}

/**
 * Ring of preallocated 8-byte buffers so high-Hz sends never allocate,
 * and overlapping async WS copies can't race a single shared buffer.
 */
const MOVE_POOL = Array.from({ length: 16 }, () => {
  const bytes = new Uint8Array(8);
  return { bytes, f32: new Float32Array(bytes.buffer) };
});
let movePoolIdx = 0;

/** Write dx/dy into the next pool slot; send the returned Uint8Array ASAP. */
export function writeMoveBinary(dx: number, dy: number): Uint8Array {
  const slot = MOVE_POOL[movePoolIdx];
  movePoolIdx = (movePoolIdx + 1) % MOVE_POOL.length;
  slot.f32[0] = dx;
  slot.f32[1] = dy;
  return slot.bytes;
}

/** Detached copy when a consumer must own the buffer. */
export function encodeMoveBinary(dx: number, dy: number): ArrayBuffer {
  const src = writeMoveBinary(dx, dy);
  return src.buffer.slice(src.byteOffset, src.byteOffset + 8) as ArrayBuffer;
}

export function buildWsUrl(host: string, port: number = DEFAULT_PORT): string {
  const cleaned = normalizeHostInput(host);
  if (!cleaned) return `ws://127.0.0.1:${port}`;
  // IPv6 [::1] or host:port already present
  if (cleaned.startsWith('[') || /:\d+$/.test(cleaned)) {
    return `ws://${cleaned}`;
  }
  if (cleaned.includes(':') && !cleaned.startsWith('[')) {
    return `ws://${cleaned}`;
  }
  return `ws://${cleaned}:${port}`;
}
