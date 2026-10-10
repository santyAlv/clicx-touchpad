"""ClicX quick actions (Fase 1).

Implements the ``{"t":"action","name":...}`` domain with host-side double
confirmation for dangerous actions (lock/shutdown/restart/sleep/logout).

DANGEROUS actions never run directly: the client must ARM then CONFIRM within a
short window (host side). This is the plan's "doble confirmación (UI + host) + timeout".

This module performs real OS actions only when explicitly armed+confirmed. The unit
tests exercise the guard logic and harmless actions; they never trigger shutdown.
"""

from __future__ import annotations

import ctypes
import os
import time
from dataclasses import dataclass
from typing import Callable

# --- Action categories -----------------------------------------------------
#: Actions that always require arm-then-confirm with a timeout.
DANGEROUS: frozenset[str] = frozenset(
    {"lock", "shutdown", "restart", "sleep", "logout"}
)
#: Harmless / safe actions run immediately (no double confirmation needed).
SAFE: frozenset[str] = frozenset({"desktop", "screenshot"})

ALL: frozenset[str] = DANGEROUS | SAFE

#: Seconds to confirm a dangerous action before the arm expires.
CONFIRM_WINDOW_S = 10.0


def _lock():
    ctypes.windll.user32.LockWorkStation()


def _shutdown():
    # /t 3 gives a short grace so a stray confirm doesn't kill instantly.
    os.system("shutdown /s /t 3")


def _restart():
    os.system("shutdown /r /t 3")


def _logout():
    # EWX_LOGOFF = 0
    ctypes.windll.user32.ExitWindowsEx(0, 0)


def _sleep():
    try:
        # SetSuspendState(Hibernate, ForceCritical, DisableWakeEvent)
        ctypes.windll.powrprof.SetSuspendState(0, 0, 0)
    except Exception:  # noqa: BLE001
        pass


def _press_win_d():
    # Minimal Win+D ("show desktop") via keybd_event (same as main.press_hotkey).
    user32 = ctypes.windll.user32
    user32.keybd_event(0x5B, 0, 0, 0)  # VK_LWIN down
    user32.keybd_event(0x44, 0, 0, 0)  # 'D' down
    user32.keybd_event(0x44, 0, 0x0002, 0)  # 'D' up
    user32.keybd_event(0x5B, 0, 0x0002, 0)  # VK_LWIN up


def _screenshot():
    """Save a full-screen PNG to C:\\ClicX\\Captures and return the path."""
    try:
        from PIL import ImageGrab
    except Exception:  # noqa: BLE001
        return None
    try:
        folder = os.path.join("C:\\", "ClicX", "Captures")
        os.makedirs(folder, exist_ok=True)
        name = time.strftime("clicx-%Y%m%d-%H%M%S.png")
        path = os.path.join(folder, name)
        ImageGrab.grab().save(path)
        return path
    except Exception:  # noqa: BLE001
        return None


_IMPLEMENTATIONS: dict[str, Callable[[], object]] = {
    "lock": _lock,
    "shutdown": _shutdown,
    "restart": _restart,
    "logout": _logout,
    "sleep": _sleep,
    "desktop": _press_win_d,
    "screenshot": _screenshot,
}


@dataclass
class ActionGuard:
    """Host-side confirmation state for one dangerous action."""

    armed_at: float = 0.0
    armed_action: str | None = None

    def arm(self, name: str, now: float | None = None) -> None:
        self.armed_action = name
        self.armed_at = now if now is not None else time.time()

    def is_armed(self, name: str, now: float | None = None) -> bool:
        if self.armed_action != name:
            return False
        now = now if now is not None else time.time()
        return (now - self.armed_at) <= CONFIRM_WINDOW_S

    def clear(self) -> None:
        self.armed_action = None
        self.armed_at = 0.0


def handle_action(
    data: dict,
    *,
    guard: ActionGuard | None = None,
    now: float | None = None,
) -> dict:
    """Process one ``t:action`` message and return a reply payload (dict).

    ``now`` is injectable for tests.
    """
    guard = guard or ActionGuard()
    name = str(data.get("name", ""))
    ok_name = name.lower()
    if ok_name not in ALL:
        return {"t": "action", "action": name, "ok": False, "error": "unknown"}
    cmd = str(data.get("confirm", "")).lower()

    if ok_name in SAFE:
        result = _safe_run(ok_name)
        return {
            "t": "action",
            "action": ok_name,
            "ok": True,
            "result": result if result is not None else True,
        }

    # Dangerous: require arm-then-confirm.
    if cmd == "prepare":
        guard.arm(ok_name, now)
        return {
            "t": "action",
            "action": ok_name,
            "phase": "armed",
            "ok": False,  # not executed yet; phone must confirm
            "timeout": CONFIRM_WINDOW_S,
        }
    if cmd == "go":
        if not guard.is_armed(ok_name, now):
            return {
                "t": "action",
                "action": ok_name,
                "phase": "expired",
                "ok": False,
                "error": "confirmation window expired",
            }
        guard.clear()
        _run_impl(ok_name)
        return {"t": "action", "action": ok_name, "phase": "done", "ok": True}

    return {
        "t": "action",
        "action": ok_name,
        "phase": "need-prepare",
        "ok": False,
        "error": "dangerous action requires prepare then confirm",
    }


def _safe_run(name: str):
    return _run_impl(name)


def _run_impl(name: str):
    fn = _IMPLEMENTATIONS.get(name)
    if fn is None:
        return None
    try:
        return fn() or True
    except Exception:  # noqa: BLE001
        return False
