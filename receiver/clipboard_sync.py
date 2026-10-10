"""ClicX shared clipboard (Fase 2).

Implements ``{"t":"clipboard","action":...}`` with:
  set / push_back / history / clear / sync

Design decisions per plan §2.9 and §4:
  * Auto-sync is OFF by default; the phone must explicitly enable it per connection.
  * History is kept ONLY in memory (never written to disk) and is erasable via
    ``clear``. It is capped (``_HISTORY_MAX`` entries, FIFO).
  * The clipboard CONTENT is NEVER logged or printed; only non-content facts
    (action + length) may appear in logs, and even those are kept minimal.
  * Windows clipboard access uses the same ctypes CF_UNICODETEXT pattern already
    present in main.py (``_clipboard_paste``) so no new dependency is added.

Wire actions (client → host -> reply):
  set        {"t":"clipboard","action":"set","text":...}      -> set_ack
  push_back  {"t":"clipboard","action":"push_back"}           -> push(text, ts)   (Copy PC→Phone)
  history    {"t":"clipboard","action":"history"}             -> history(items[])
  clear      {"t":"clipboard","action":"clear"}               -> clear_ack
  sync       {"t":"clipboard","action":"sync","on":bool}      -> sync_ack

Auto-sync: when enabled by a client, a lazy daemon thread polls the PC clipboard
and pushes changes (``push(text, ts)``) to that client. No content is ever logged.
"""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from ctypes import wintypes
from typing import Any, Callable

#: Max history entries kept in memory (FIFO).
_HISTORY_MAX = 20
#: Auto-sync poll interval.
_POLL_S = 1.5
#: Messages that require content; anything outside this list is rejected.
_ACTIONS = ("set", "push_back", "history", "clear", "sync")

_history_lock = threading.Lock()
_history: list[dict[str, Any]] = []

_sync_lock = threading.Lock()
_sync_on: dict[Any, bool] = {}  # conn key -> auto-sync enabled
_last_text: dict[Any, str] = {}  # conn key -> last pushed text (change detection)
_watcher_started = False
_watcher_lock = threading.Lock()

# IO seam: real Windows clipboard ops (installed at import). Tests replace these
# globals afterwards so no real clipboard side effects happen in the suite.
_get_clipboard_text: Callable[[], str] = lambda: ""
_set_clipboard_text: Callable[[str], bool] = lambda text: False


# ---------------------------------------------------------------------------
# Windows clipboard (ctypes CF_UNICODETEXT — same pattern as main.py)
# ---------------------------------------------------------------------------

def _win_clipboard_text() -> str:
    """Return current Windows clipboard text ('' if not available)."""
    CF_UNICODETEXT = 13
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [ctypes.c_uint]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    if not user32.OpenClipboard(None):
        return ""
    try:
        data = user32.GetClipboardData(CF_UNICODETEXT)
        if not data:
            return ""
        size = kernel32.GlobalSize(data)
        ptr = kernel32.GlobalLock(data)
        if not ptr:
            return ""
        try:
            # UTF-16 text contains interleaved NUL bytes, so we must read the
            # whole block via GlobalSize, not string_at (which stops at the
            # first NUL).
            raw = ctypes.string_at(ptr, size)
        finally:
            kernel32.GlobalUnlock(data)
        try:
            return raw.decode("utf-16-le", errors="ignore").rstrip("\x00")
        except Exception:  # noqa: BLE001
            return ""
    finally:
        user32.CloseClipboard()


def _win_set_clipboard_text(text: str) -> bool:
    """Write Unicode text to the Windows clipboard (no paste, no typing)."""
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [ctypes.c_uint, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL
    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        payload = text.encode("utf-16-le") + b"\x00\x00"
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(payload))
        if not h_mem:
            return False
        ptr = kernel32.GlobalLock(h_mem)
        if not ptr:
            kernel32.GlobalFree(h_mem)
            return False
        try:
            ctypes.memmove(ptr, payload, len(payload))
        finally:
            kernel32.GlobalUnlock(h_mem)
        if not user32.SetClipboardData(CF_UNICODETEXT, h_mem):
            kernel32.GlobalFree(h_mem)
            return False
        return True
    finally:
        user32.CloseClipboard()


def _install_win_impl() -> None:
    """Wire the module-level IO globals to the real Windows clipboard (test seam)."""
    global _get_clipboard_text, _set_clipboard_text
    if sys.platform.startswith("win"):
        _get_clipboard_text = _win_clipboard_text
        _set_clipboard_text = _win_set_clipboard_text


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

def _add_history(text: str, ts: float) -> None:
    """Record a clipboard entry in memory only. Never persist, never log content."""
    with _history_lock:
        _history.insert(0, {"ts": ts, "len": len(text), "text": text})
        del _history[_HISTORY_MAX:]


def _history_items() -> list[dict[str, Any]]:
    with _history_lock:
        return [
            {"ts": item["ts"], "len": item["len"], "text": item["text"]}
            for item in _history
        ]


def _clear_history() -> None:
    with _history_lock:
        _history.clear()


# ---------------------------------------------------------------------------
# Auto-sync watcher (lazy daemon thread, OFF until a client enables it)
# ---------------------------------------------------------------------------

def _watcher_loop() -> None:
    while True:
        try:
            with _sync_lock:
                targets = [conn for conn, on in _sync_on.items() if on]
            if targets:
                current = _get_clipboard_text()
                for conn in targets:
                    last = _last_text.get(conn, None)
                    if current and current != last:
                        _last_text[conn] = current
                        _add_history(current, time.time())
                        _push_to(conn, current)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(_POLL_S)


def _ensure_watcher() -> None:
    global _watcher_started
    with _watcher_lock:
        if _watcher_started:
            return
        _watcher_started = True
        threading.Thread(target=_watcher_loop, name="clicx-clipboard", daemon=True).start()


def _push_sentinel_pending(conn: Any) -> None:
    """Nothing pending; kept for symmetry with file_transfer cleanup calls."""
    with _sync_lock:
        _sync_on.pop(conn, None)
        _last_text.pop(conn, None)


# ---------------------------------------------------------------------------
# Entry point (dispatcher-friendly)
# ---------------------------------------------------------------------------

def handle_clipboard(data: dict[str, Any], websocket: Any = None) -> dict | None:
    """Handle a ``t:"clipboard"`` message.

    Returns the JSON reply dict (sent back by the caller) or None for
    fire-and-forget paths. Auto-sync pushes are sent directly over ``websocket``.
    Never logs clipboard content.
    """
    action = str(data.get("action", "")).lower()
    if action not in _ACTIONS:
        return {"t": "clipboard", "action": action, "ok": False, "error": "unknown"}

    if action == "set":
        text = data.get("text")
        if not isinstance(text, str):
            return {"t": "clipboard", "action": action, "ok": False, "error": "bad text"}
        # Do NOT echo the text anywhere except the clipboard itself.
        ok = _set_clipboard_text(text)
        _add_history(text, time.time())
        if ok and websocket is not None:
            with _sync_lock:
                if _sync_on.get(websocket):
                    _last_text[websocket] = text
        return {"t": "clipboard", "action": action, "ok": ok}

    if action == "push_back":
        text = _get_clipboard_text()
        _add_history(text, time.time())
        return {
            "t": "clipboard",
            "action": "push",
            "text": text,
            "ts": time.time(),
        }

    if action == "history":
        return {"t": "clipboard", "action": "history", "items": _history_items()}

    if action == "clear":
        _clear_history()
        return {"t": "clipboard", "action": action, "ok": True}

    if action == "sync":
        on = bool(data.get("on", False))
        if websocket is not None:
            with _sync_lock:
                _sync_on[websocket] = on
                if on:
                    _last_text.setdefault(websocket, _get_clipboard_text())
            if on:
                _ensure_watcher()
        else:
            # No websocket (test path): toggling without a conn is harmless.
            pass
        return {"t": "clipboard", "action": action, "ok": True, "on": on}

    return {"t": "clipboard", "action": action, "ok": False, "error": "unknown"}


def _push_to(conn: Any, text: str) -> None:
    """Push a clipboard change to a specific client (auto-sync)."""
    if not text:
        return
    payload = json_dumps(
        {"t": "clipboard", "action": "push", "text": text, "ts": time.time()}
    )
    try:
        conn.send(payload)
    except Exception:  # noqa: BLE001
        pass


def json_dumps(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload)


def cleanup_connection(conn: Any) -> None:
    """Remove per-connection auto-sync state on disconnect. Never raises."""
    try:
        _push_sentinel_pending(conn)
    except Exception:  # noqa: BLE001
        pass


# Install the real Windows clipboard implementation at import time. Unit tests
# import this module on Windows and can still override _get/_set_clipboard_text.
_install_win_impl()