import { DEFAULT_PORT } from './protocol';

export type ConnectTarget = { host: string; port: number };

/** Parse QR / pasted payload: clicx://, ws://, or JSON. */
export function parseConnectPayload(raw: string): ConnectTarget | null {
  const text = raw.trim();
  if (!text) return null;

  // clicx://connect?host=192.168.1.1&port=51234
  if (/^clicx:\/\//i.test(text)) {
    try {
      const url = new URL(text.replace(/^clicx:/i, 'https:'));
      const host = url.searchParams.get('host')?.trim();
      const port = Number(url.searchParams.get('port') || DEFAULT_PORT);
      if (host) return { host, port: Number.isFinite(port) ? port : DEFAULT_PORT };
    } catch {
      /* fall through */
    }
  }

  // ws://192.168.1.1:51234
  const ws = text.match(/^wss?:\/\/([^/:]+)(?::(\d+))?/i);
  if (ws) {
    return {
      host: ws[1],
      port: ws[2] ? Number(ws[2]) : DEFAULT_PORT,
    };
  }

  // JSON {"host":"...","port":51234}
  if (text.startsWith('{')) {
    try {
      const j = JSON.parse(text) as { host?: string; port?: number };
      if (j.host) {
        return {
          host: String(j.host).trim(),
          port: Number(j.port) || DEFAULT_PORT,
        };
      }
    } catch {
      /* fall through */
    }
  }

  // bare IP[:port]
  const bare = text.match(/^(\d{1,3}(?:\.\d{1,3}){3})(?::(\d+))?$/);
  if (bare) {
    return {
      host: bare[1],
      port: bare[2] ? Number(bare[2]) : DEFAULT_PORT,
    };
  }

  return null;
}

export function buildConnectQrPayload(host: string, port: number): string {
  return `clicx://connect?host=${encodeURIComponent(host)}&port=${port}`;
}
