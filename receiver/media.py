"""ClicX media transport (Fase 1).

Implements ``{"t":"media","action":...}`` using standard Windows multimedia virtual
keys (VK_MEDIA_*) — no per-app integrations, per plan §2.14.

Volume handling is intentionally NOT reimplemented here: the existing ``t:volume``
domain (main.py handle_volume_message + VolumePill) already manages the general
volume, and this module must not duplicate it. So ``media`` only covers transport
(play_pause|prev|next|stop) with the standard keys Windows routes to the current
media session.
"""

from __future__ import annotations

import ctypes
from typing import Any

# Windows multimedia VKs (see winuser.h).
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_MEDIA_STOP = 0xB2

KEYEVENTF_KEYUP = 0x0002

_ACTIONS: dict[str, int] = {
    "play_pause": VK_MEDIA_PLAY_PAUSE,
    "next": VK_MEDIA_NEXT_TRACK,
    "prev": VK_MEDIA_PREV_TRACK,
    "stop": VK_MEDIA_STOP,
}


def _tap(vk: int) -> None:
    user32 = ctypes.windll.user32
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def handle_media(data: dict[str, Any]) -> dict:
    """Handle one ``t:media`` message; returns a reply payload.

    Unsupported/invalid actions return an error reply instead of raising.
    Volume-ish media actions (mute/vol_up/vol_down) are out of scope here; point the
    client at the existing ``t:volume`` domain. We accept and reject them explicitly
    so the client gets a clear signal.
    """
    action = str(data.get("action", "")).lower()
    if action in _ACTIONS:
        _tap(_ACTIONS[action])
        return {"t": "media", "action": action, "ok": True}
    if action in ("mute", "vol_up", "vol_down"):
        return {
            "t": "media",
            "action": action,
            "ok": False,
            "error": "use t:volume",
        }
    return {"t": "media", "action": action, "ok": False, "error": "unknown"}
