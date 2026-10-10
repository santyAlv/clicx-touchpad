import { useCallback, useEffect, useRef, useState } from 'react';
import { parseHostDeck, type DeckPage } from './deckConfig';
import type { ClicxMessage } from './protocol';
import { setAccent } from './palette';
import { buildWsUrl, CONNECT_TIMEOUT_MS, DEFAULT_PORT, writeMoveBinary } from './protocol';

export type ConnStatus = 'idle' | 'connecting' | 'connected' | 'error';

export type HostFeatures = {
  protocol?: string;
  domains?: Record<string, boolean>;
};

/**
 * Single WebSocket for moves + clicks.
 */
export function useClicxConnection() {
  const wsRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<ConnStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [hostInfo, setHostInfo] = useState<string | null>(null);
  const [textFieldFocused, setTextFieldFocused] = useState(false);
  const [deckPages, setDeckPages] = useState<DeckPage[] | null>(null);
  const [features, setFeatures] = useState<HostFeatures | null>(null);
  const replyListeners = useRef(new Set<(data: Record<string, unknown>) => void>());
  const binaryListeners = useRef(new Set<(data: ArrayBuffer) => void>());

  const disconnect = useCallback(() => {
    const ws = wsRef.current;
    wsRef.current = null;
    if (ws) {
      ws.onopen = null;
      ws.onclose = null;
      ws.onerror = null;
      ws.onmessage = null;
      try {
        ws.close();
      } catch {
        // ignore
      }
    }
    setStatus('idle');
    setHostInfo(null);
    setTextFieldFocused(false);
    setDeckPages(null);
    setFeatures(null);
    replyListeners.current.clear();
    binaryListeners.current.clear();
  }, []);

  const connect = useCallback(
    (host: string, port: number = DEFAULT_PORT) => {
      disconnect();
      setError(null);
      setStatus('connecting');
      setTextFieldFocused(false);

      const url = buildWsUrl(host, port);
      let ws: WebSocket;
      try {
        ws = new WebSocket(url);
      } catch (e) {
        setStatus('error');
        setError(e instanceof Error ? e.message : 'No se pudo crear WebSocket');
        return;
      }

      try {
        ws.binaryType = 'arraybuffer';
      } catch {
        // ignore
      }

      wsRef.current = ws;
      let opened = false;
      let settled = false;

      const fail = (message: string) => {
        if (settled || wsRef.current !== ws) return;
        settled = true;
        clearTimeout(timeout);
        setStatus('error');
        setError(message);
        try {
          ws.close();
        } catch {
          // ignore
        }
      };

      const timeout = setTimeout(() => {
        fail(
          'No se pudo conectar. Misma Wi‑Fi que la PC, IP correcta, host iniciado y firewall permitido.',
        );
      }, CONNECT_TIMEOUT_MS);

      ws.onopen = () => {
        if (wsRef.current !== ws) return;
        settled = true;
        clearTimeout(timeout);
        opened = true;
        setStatus('connected');
      };

      ws.onmessage = (ev) => {
        // Raw binary frames (file-transfer data / future screen frames).
        if (ev.data instanceof ArrayBuffer || ArrayBuffer.isView(ev.data)) {
          const buf = (ev.data instanceof ArrayBuffer
            ? ev.data
            : (ev.data as ArrayBufferView).buffer) as ArrayBuffer;
          const listeners = binaryListeners.current;
          if (listeners.size === 0) return;
          for (const cb of Array.from(listeners)) {
            try {
              cb(buf);
            } catch {
              // ignore
            }
          }
          return;
        }
        try {
          const data = JSON.parse(String(ev.data));
          if (data?.t === 'deckSync' || data?.t === 'deck') {
            const parsed = parseHostDeck(data.deck);
            if (parsed?.pages) setDeckPages(parsed.pages);
            setAccent(data.deck?.accent);
          }
          if (data?.t === 'hello') {
            setHostInfo(`${data.name ?? 'ClicX'} v${data.version ?? '?'}`);
            const parsed = parseHostDeck(data.deck);
            setDeckPages(parsed?.pages ?? null);
            setAccent(data.deck?.accent);
            if (data.features) {
              setFeatures({
                protocol: String(data.features.protocol ?? data.protocol ?? ''),
                domains: data.features.domains ?? {},
              });
            }
          }
          if (data?.t === 'editable') {
            setTextFieldFocused(Boolean(data.on));
          }
          if (data?.t === 'error' && data.msg) {
            setError(String(data.msg));
          }
          // Notify reply subscribers (status/action/media/app_volume/windows).
          const listeners = replyListeners.current;
          if (listeners.size > 0) {
            const obj = data as Record<string, unknown>;
            for (const cb of Array.from(listeners)) {
              try {
                cb(obj);
              } catch {
                // ignore
              }
            }
          }
        } catch {
          // ignore binary/non-json
        }
      };

      ws.onerror = () => {
        if (wsRef.current !== ws || settled) return;
        fail(
          'Error de red. Revisá IP/puerto, misma Wi‑Fi y que el host esté escuchando.',
        );
      };

      ws.onclose = () => {
        clearTimeout(timeout);
        if (wsRef.current !== ws) return;
        wsRef.current = null;
        setTextFieldFocused(false);
        if (settled) {
          if (opened) setStatus('idle');
          return;
        }
        settled = true;
        setStatus('error');
        setError('Conexión rechazada. ¿Host encendido y en la misma red?');
      };
    },
    [disconnect],
  );

  const sendMove = useCallback((dx: number, dy: number) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    try {
      ws.send(writeMoveBinary(dx, dy));
    } catch {
      try {
        ws.send(`m,${dx},${dy}`);
      } catch {
        // ignore
      }
    }
  }, []);

  const sendClick = useCallback(
    (btn: 'left' | 'right' | 'middle' = 'left', n: number = 1) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      const count = Math.max(1, Math.min(3, n | 0));
      const payload = JSON.stringify({ t: 'click', btn, n: count });
      try {
        ws.send(payload);
      } catch {
        // ignore
      }
    },
    [],
  );

  const send = useCallback(
    (msg: ClicxMessage) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      if (msg.t === 'move') {
        sendMove(msg.dx, msg.dy);
        return;
      }
      if (msg.t === 'click') {
        sendClick(msg.btn, msg.n ?? 1);
        return;
      }
      try {
        ws.send(JSON.stringify(msg));
      } catch {
        // ignore
      }
    },
    [sendMove, sendClick],
  );

  useEffect(() => () => disconnect(), [disconnect]);

  const onReply = useCallback(
    (cb: (data: Record<string, unknown>) => void) => {
      replyListeners.current.add(cb);
      return () => {
        replyListeners.current.delete(cb);
      };
    },
    [],
  );

  const onBinary = useCallback((cb: (data: ArrayBuffer) => void) => {
    binaryListeners.current.add(cb);
    return () => {
      binaryListeners.current.delete(cb);
    };
  }, []);

  /** Send a raw JSON string (for control messages outside the ClicxMessage union). */
  const sendString = useCallback((data: string) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    try {
      ws.send(data);
    } catch {
      // ignore
    }
  }, []);

  /** Send a raw binary frame (file-transfer chunks). */
  const sendBinary = useCallback((data: ArrayBuffer | Uint8Array) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    try {
      ws.send(data);
    } catch {
      // ignore
    }
  }, []);

  return {
    status,
    error,
    hostInfo,
    textFieldFocused,
    deckPages,
    features,
    connect,
    disconnect,
    send,
    sendMove,
    sendClick,
    sendString,
    sendBinary,
    onReply,
    onBinary,
  };
}
