# ClicX protocol v0.8

WebSocket `ws://<ip>:51234` (+ USB via `adb reverse` → `ws://127.0.0.1:51234`).
Optional UDP `<ip>:51235` (8-byte moves).

## Pairing

QR / paste payload (host “Mostrar QR”):

```
clicx://connect?host=192.168.1.20&port=51234
```

Also accepted: `ws://host:port`, bare `host:port`, JSON `{"host":"...","port":51234}`.

## USB (Android)

1. Host: **Activar USB** → `adb reverse tcp:51234 tcp:51234`
2. App: modo **Cable USB** → Connect to `127.0.0.1:51234`

## Hello (capability detection)

On connect the host sends a single `hello` message. Beyond `name`/`version`/`deck`,
it now advertises `protocol` and `features` so the phone can detect which domains the
host supports and avoid sending unsupported `t` types:

```json
{
  "t": "hello",
  "name": "ClicX",
  "version": "0.8.0",
  "deck": { "version": 1 },
  "protocol": "0.8",
    "features": {
    "protocol": "0.8",
    "domains": {
      "touchpad": true,
      "keyboard": true,
      "deck": true,
      "volume_general": true,
      "windows": true,
      "app_volume": true,
      "status": true,
      "actions": true,
      "media": true,
      "clipboard": true,
      "file": true
    }
  }
}
```

`features.domains` keys turn `true` as each domain is implemented (Fase 1+). A client
should treat `false`/missing as "not available yet" and not send those `t` messages.

## Latency stack

- Sync WebSocket server (no asyncio between frames)
- TCP_NODELAY
- Dual client sockets: moves vs control (less HOL blocking)
- Win32 SendInput + sub-pixel remainder
- Optional prediction lead (`CLICX_PRED_MS`; see host for the live default)
- UDP port ready for native clients

## Move frame

8 bytes LE float32 `dx`, `dy` (binary WS or UDP).

## JSON messages

See [`examples.json`](examples.json).

`{"t":"stop"}` — clear host prediction on finger-up.

## Clipboard (`t:"clipboard"`)

Explicit, OFF by default; the phone must enable auto-sync per connection. The host
keeps history **in memory only** (erasable, never persisted) and never logs content.

| Direction | Message | Reply |
| --- | --- | --- |
| C→H | `{"t":"clipboard","action":"set","text":"..."}` | `{"t":"clipboard","action":"set","ok":true}` |
| C→H | `{"t":"clipboard","action":"push_back"}` | `{"t":"clipboard","action":"push","text":"...","ts":...}` (Copy PC→Phone) |
| C→H | `{"t":"clipboard","action":"history"}` | `{"t":"clipboard","action":"history","items":[{ts,len,text},...]}` |
| C→H | `{"t":"clipboard","action":"clear"}` | `{"t":"clipboard","action":"clear","ok":true}` |
| C→H | `{"t":"clipboard","action":"sync","on":true\|false}` | `{"t":"clipboard","action":"sync","ok":true,"on":...}` |
| H→C | `{"t":"clipboard","action":"push","text":"...","ts":...}` | (auto-sync, when enabled) |

History is capped (20 entries, FIFO). `set` writes the text to the PC clipboard
(no keyboard typing). Content is never written to logs.

## File transfer (`t:"file"`)

JSON control + raw binary frames over the same WebSocket (never Base64). Two fixed
folders only: `<root>/From Phone` (phone→PC) and `<root>/From PC` (PC→phone), with
`<root>` = `%LOCALAPPDATA%\ClicX` unless `CLICX_TRANSFER_ROOT` overrides it.

Validation happens on the host: basename only, no `../`/absolute/drive paths, no
reserved names, extension blocklist for PC uploads (`.exe`, `.ps1`, …), size ≤ 200 MiB,
chunk ≤ 64 KiB, offsets must match the stream, cancel/timeout/cleanup of partials.

**Upload (phone→PC):**
```
C→H { "t":"file","action":"meta","id":"u1","name":"foto.jpg","size":123456 }
H→C { "t":"file","action":"meta_ack","ok":true,"id":"u1","offset":0 }
C→H { "t":"file","action":"chunk","id":"u1","offset":0,"size":65536 }  + <binary>
H→C { "t":"file","action":"chunk_ack","ok":true,"id":"u1","received":65536 }
... (repeat per chunk)
C→H { "t":"file","action":"done","id":"u1" }   |  { "t":"file","action":"cancel","id":"u1" }
H→C { "t":"file","action":"done_ack","ok":true,"id":"u1" } | { "t":"file","action":"cancel_ack","ok":true,"id":"u1" }
```

**Download (PC→phone):**
```
C→H { "t":"file","action":"list","folder":"from_pc" }
H→C { "t":"file","action":"list","folder":"from_pc","files":[{name,size},...] }
C→H { "t":"file","action":"download","id":"d1","name":"report.pdf" }
H→C { "t":"file","action":"meta","ok":true,"id":"d1","name":"report.pdf","size":2048 }
C→H { "t":"file","action":"pull","id":"d1","size":65536 }
H→C { "t":"file","action":"chunk","ok":true,"id":"d1","offset":0,"size":2048 } + <binary>
H→C { "t":"file","action":"done","ok":true,"id":"d1" }   (when the source is exhausted)
```

The receiver correlates an armed binary frame with the session from the *last*
`chunk` JSON; binary frames with no armed session are the 8-byte move stream, so file
data never collides with touchpad moves.
