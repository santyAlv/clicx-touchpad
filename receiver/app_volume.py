"""ClicX per-application volume control (Fase 1).

Implements ``{"t":"app_volume","action":...}`` with ``list``/``set``/``mute`` per
audio *session* via pycaw's ``AudioUtilities``. This is SEPARATE from the general
(master) volume already handled by ``main.py`` / ``VolumePill`` (``t:volume``) — it
never touches the master endpoint volume.

Limitations (documented per plan §2.23): pycaw exposes a display-name only for a
subset of sessions; device/rendering info beyond that may be unreliable, so we expose
a stable ``id`` (the audio session pid), ``name`` (exe or session display name),
``volume`` (0..100) and ``muted``. If pycaw fails, the module degrades gracefully
(empty list) instead of crashing the host.
"""

from __future__ import annotations

from typing import Any


def _audio_mgr():
    """Lazy pycaw AudioUtilities — returns None if unavailable/error."""
    try:
        from pycaw.pycaw import AudioUtilities  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    return AudioUtilities


def _safe_float(value, default=0.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError, AttributeError):
        return default
    return v


def _session_volume(session) -> float:
    sav = getattr(session, "SimpleAudioVolume", None)
    if sav is None:
        return 0.0
    try:
        # pycaw returns master volume as 0.0..1.0 via GetMasterVolume().
        v = _safe_float(sav.GetMasterVolume(), 0.0)
        return max(0.0, min(1.0, v)) * 100.0
    except Exception:  # noqa: BLE001
        return 0.0


def _session_muted(session) -> bool:
    sav = getattr(session, "SimpleAudioVolume", None)
    if sav is None:
        return False
    try:
        return bool(sav.GetMute())
    except Exception:  # noqa: BLE001
        return False


def _session_name(session) -> str:
    proc = getattr(session, "Process", None)
    try:
        if proc is not None:
            name = proc.name()
            if name:
                return name
    except Exception:  # noqa: BLE001
        pass
    try:
        name = session.DisplayName
        if name:
            return name
    except Exception:  # noqa: BLE001
        pass
    return "Unknown"


def _session_id(session, fallback: int) -> int:
    proc = getattr(session, "Process", None)
    for attr in ("pid", "id"):
        try:
            v = getattr(session, attr, None) or getattr(proc, attr, None)
            if isinstance(v, int) and v > 0:
                return v
        except Exception:  # noqa: BLE001
            continue
    return fallback


def _iter_sessions():
    """Yield (session) objects; never raises."""
    AudioUtilities = _audio_mgr()
    if AudioUtilities is None:
        return
    try:
        sessions = AudioUtilities.GetAllSessions()
    except Exception:  # noqa: BLE001
        return
    if not sessions:
        return
    for s in sessions:
        try:
            state = getattr(s, "State", 1)
            # Render sessions: STATE_ACTIVE=1 or STATE_MUTED=2; skip connectors/expired.
            if state in (1, 2):
                yield s
        except Exception:  # noqa: BLE001
            continue


def list_apps() -> list[dict[str, Any]]:
    apps: list[dict[str, Any]] = []
    fallback = 0
    for s in _iter_sessions():
        fallback += 1
        pid = _session_id(s, fallback)
        apps.append(
            {
                "id": pid,
                "name": _session_name(s),
                "volume": round(_session_volume(s), 0),
                "muted": _session_muted(s),
            }
        )
    return apps


def _find_session(target_id: int):
    fallback = 0
    for s in _iter_sessions():
        fallback += 1
        if _session_id(s, fallback) == target_id:
            return s
    return None


def _apply_to(session, *, volume: float | None = None, muted: bool | None = None) -> bool:
    sav = getattr(session, "SimpleAudioVolume", None)
    if sav is None:
        return False
    changed = False
    try:
        if volume is not None:
            v = max(0.0, min(1.0, volume / 100.0))
            sav.SetMasterVolume(v, None)
            changed = True
        if muted is not None:
            sav.SetMute(1 if muted else 0, None)
            changed = True
        return changed
    except Exception:  # noqa: BLE001
        return False


def handle_app_volume(data: dict[str, Any]) -> dict:
    action = str(data.get("action", "")).lower()

    if action == "list":
        return {"t": "app_volume", "action": "list", "apps": list_apps()}

    if action in ("set", "mute"):
        raw_id = data.get("id")
        try:
            target = int(raw_id)
        except (TypeError, ValueError, AttributeError):
            return {"t": "app_volume", "action": action, "ok": False, "error": "bad id"}
        session = _find_session(target)
        if session is None:
            return {
                "t": "app_volume",
                "action": action,
                "ok": False,
                "error": "session not found",
            }
        volume = None
        muted = None
        if action == "set":
            raw_v = data.get("volume")
            try:
                volume = float(raw_v)
            except (TypeError, ValueError):
                return {"t": "app_volume", "action": action, "ok": False, "error": "bad volume"}
        else:
            muted = bool(data.get("muted", False))
        ok = _apply_to(session, volume=volume, muted=muted)
        return {"t": "app_volume", "action": action, "ok": ok, "id": target}

    return {"t": "app_volume", "action": action, "ok": False, "error": "unknown"}
