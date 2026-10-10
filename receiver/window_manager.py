"""ClicX open-window management (Fase 1).

Implements ``{"t":"windows","action":...}``:
  list / focus / minimize / maximize / restore / close / foreground

Uses Win32 via ctypes (same pattern as icon_extract.py / main.py) so no new
dependency. Windows are exposed with a safe internal ``id`` (the HWND integer) and
minimal info (title, app, active, minimized) — no PID or unnecessary detail is sent
for the phone list.

Safety (per plan §2.22):
  * Critical/shell windows (desktop, taskbar, etc.) are excluded from ``list`` and
    blocked from ``close``/``minimize``.
  * ``close`` targets are validated; a reduced set of classes is hard-blocked.
  * List enumeration is cached ~1s so client polling doesn't regenerate it per frame.

Architecture note: ``pos {x,y,w,h}`` and ``move|resize`` are reserved for a future
phase; they are not implemented but the message shape doesn't break if a client sends
them (we ignore unknown sub-actions with an error reply).
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Any

# --- Win32 constants ---
GWL_STYLE = -16
WS_MINIMIZE = 0x20000000
WS_MAXIMIZE = 0x01000000

SW_SHOW = 5
SW_RESTORE = 9
SW_MINIMIZE = 6
SW_MAXIMIZE = 3
SW_HIDE = 0

WM_CLOSE = 0x0010

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

#: Window classes that are part of the desktop shell / critical infra. They must not
#: appear in the list and must never be closed or minimized.
_CRITICAL_CLASSES = frozenset(
    {
        "Progman",           # desktop
        "WorkerW",           # desktop wallpaper host
        "Shell_TrayWnd",     # taskbar
        "Shell_SecondaryTrayWnd",
        "Button",            # start-menu buttons in some builds
    }
)

#: Power-user frames we refuse to close regardless.
_NEVER_CLOSE_CLASSES = frozenset({"Progman", "WorkerW", "Shell_TrayWnd", "#32770"})

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def _window_visible(hwnd: int) -> bool:
    try:
        return bool(user32.IsWindowVisible(hwnd))
    except Exception:  # noqa: BLE001
        return False


def _window_rect(hwnd: int):
    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    r = RECT()
    try:
        user32.GetWindowRect(hwnd, ctypes.byref(r))
    except Exception:  # noqa: BLE001
        return None
    return r


def _window_text(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(512)
    try:
        n = user32.GetWindowTextW(hwnd, buf, 512)
        return buf.value[: n] if n > 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def _window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    try:
        user32.GetClassNameW(hwnd, buf, 256)
        return buf.value
    except Exception:  # noqa: BLE001
        return ""


def _window_style(hwnd: int) -> int:
    try:
        return int(user32.GetWindowLongW(hwnd, GWL_STYLE))
    except Exception:  # noqa: BLE001
        return 0


def _is_minimized(hwnd: int) -> bool:
    return bool(_window_style(hwnd) & WS_MINIMIZE)


def _is_maximized(hwnd: int) -> bool:
    return bool(_window_style(hwnd) & WS_MAXIMIZE)


def _window_exe(hwnd: int) -> str:
    """Return the process image name (basename) for a window, or '' if unavailable."""
    pid = wintypes.DWORD()
    try:
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    except Exception:  # noqa: BLE001
        return ""
    if not pid.value:
        return ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            import ntpath

            return ntpath.basename(buf.value)
    except Exception:  # noqa: BLE001
        pass
    finally:
        kernel32.CloseHandle(handle)
    return ""


def _is_critical(hwnd: int) -> bool:
    return _window_class(hwnd) in _CRITICAL_CLASSES


def _enum_windows():
    """Return [(hwnd, title, cls), ...] for visible, titled, non-critical top-level windows."""
    results: list[tuple[int, str, str]] = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.restype = wintypes.BOOL

    def cb(hwnd, _lparam):
        if not _window_visible(hwnd):
            return True
        cls = _window_class(hwnd)
        if cls in _CRITICAL_CLASSES:
            return True
        title = _window_text(hwnd)
        if not title.strip():
            return True
        results.append((int(hwnd), title, cls))
        return True

    try:
        user32.EnumWindows(EnumWindowsProc(cb), 0)
    except Exception:  # noqa: BLE001
        pass
    return results


class _ListCache:
    def __init__(self, ttl: float = 1.0) -> None:
        self.ttl = ttl
        self._data: list[dict[str, Any]] | None = None
        self._at = 0.0

    def get(self, force: bool = False) -> list[dict[str, Any]]:
        now = time.time()
        if not force and self._data is not None and (now - self._at) < self.ttl:
            return self._data
        active = int(user32.GetForegroundWindow())
        windows: list[dict[str, Any]] = []
        for hwnd, title, _cls in _enum_windows():
            windows.append(
                {
                    "id": hwnd,
                    "title": title,
                    "app": _window_exe(hwnd),
                    "active": hwnd == active,
                    "minimized": _is_minimized(hwnd),
                }
            )
        # Foreground first for convenience.
        windows.sort(key=lambda w: 0 if w["active"] else 1)
        self._data = windows
        self._at = now
        return windows


_LIST_CACHE = _ListCache()


def _find_safe_window(target_id: int):
    """Return hwnd if it's a currently-listed (safe) window, else None."""
    for w in _LIST_CACHE.get(force=True):
        if w["id"] == target_id:
            return w
    return None


def list_windows(*, force: bool = False) -> dict:
    return {"t": "windows", "action": "list", "windows": _LIST_CACHE.get(force=force)}


def _obj_id(data: dict) -> int | None:
    try:
        return int(data.get("id"))
    except (TypeError, ValueError, AttributeError):
        return None


def handle_windows(data: dict[str, Any]) -> dict:
    action = str(data.get("action", "")).lower()

    if action == "list":
        return list_windows(force=bool(data.get("force")))

    if action not in (
        "focus",
        "minimize",
        "maximize",
        "restore",
        "close",
        "foreground",
    ):
        return {"t": "windows", "action": action, "ok": False, "error": "unknown"}

    target_id = _obj_id(data)
    win = _find_safe_window(target_id) if target_id is not None else None
    if win is None:
        return {"t": "windows", "action": action, "ok": False, "error": "window not found"}

    hwnd = target_id
    ok = False
    if action in ("focus", "foreground"):
        try:
            # Try to bring to front; works for most non-elevated windows.
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            ok = True
        except Exception:  # noqa: BLE001
            ok = False
    elif action == "minimize":
        ok = _show(hwnd, SW_MINIMIZE)
    elif action == "maximize":
        ok = _show(hwnd, SW_MAXIMIZE)
    elif action == "restore":
        ok = _show(hwnd, SW_RESTORE)
    elif action == "close":
        cls = _window_class(hwnd)
        if cls in _NEVER_CLOSE_CLASSES:
            return {"t": "windows", "action": action, "ok": False, "error": "protected"}
        try:
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            ok = True
        except Exception:  # noqa: BLE001
            ok = False

    # Invalidate cache so the next list reflects the change.
    _LIST_CACHE._data = None
    return {"t": "windows", "action": action, "ok": ok, "id": target_id}


def _show(hwnd: int, cmd: int) -> bool:
    try:
        user32.ShowWindow(hwnd, cmd)
        return True
    except Exception:  # noqa: BLE001
        return False
