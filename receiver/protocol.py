"""ClicX protocol helpers — message validation and capability metadata (Fase 0).

Pure module (no I/O, no side effects) so it can be imported by tests and by both
entry points (``main.py`` and ``gui_app.py``) without risk. It does NOT change the
behaviour of existing message handling; it only *describes* and *validates* the wire
format so later phases can route new ``t`` types safely.
"""

from __future__ import annotations

import json
from typing import Any

# Matches shared/protocol.md. Sube a v0.8 con el versionado de capacidades.
PROTOCOL_VERSION = "0.8"

# "t" types already handled by the host today. Derived from main.handle_message +
# handle_raw_frame (kept in sync by hand; see comments).
_EXISTING_TYPES: set[str] = {
    "move",
    "stop",
    "click",
    "down",
    "up",
    "scroll",
    "zoom",
    "gesture",
    "hotkey",
    "volume",
    "laser",
    "type",
    "key",
    "deck",
}

# "t" types planned in CLICX_IMPLEMENTATION_PLAN.md §4 (nuevos, disjuntos).
_PLANNED_TYPES: set[str] = {
    "status",
    "action",
    "media",
    "clipboard",
    "file",
    "screen",
    "scene",
    "profile",
    "auth",
    "windows",
    "app_volume",
    "usage",
}

# "hello" originates from the host (server → client), not from the client.
_HOST_TYPES: set[str] = {"hello"}

# All understood message types, including those the host emits.
KNOWN_TYPES: set[str] = _EXISTING_TYPES | _PLANNED_TYPES | _HOST_TYPES

# Capabilities advertised in "hello". The host always reports the protocol version
# and which new domains it can already serve. As Fase 1+ implements each domain it is
# toggled here (single source of truth for capability detection).
HOST_FEATURES: dict[str, Any] = {
    "protocol": PROTOCOL_VERSION,
    # Touchpad / pointer + keyboard + deck are baseline and always on.
    "domains": {
        "touchpad": True,
        "keyboard": True,
        "deck": True,
        "volume_general": True,
        # Enabled in Fase 1 (centro de control):
        "windows": True,
        "app_volume": True,
        "status": True,
        "actions": True,
        "media": True,
        # Enabled in Fase 2 (integración):
        "clipboard": True,
        "file": True,
        # Claude / Codex usage, read off the transcripts they write locally.
        "usage": True,
        # Not yet implemented (later phases):
        "screen": False,
        "gesture_custom": False,
        "scenes": False,
        "profiles": False,
        "auth": False,
    },
}


def known_type(t: str) -> bool:
    """True if ``t`` is a message kind this host understands (existing or planned)."""
    return t in KNOWN_TYPES


def is_planned_type(t: str) -> bool:
    """True if ``t`` is declared in the plan but not yet implemented by the host."""
    return t in _PLANNED_TYPES


def validate_message(data: Any) -> list[str]:
    """Return a list of human-readable validation problems.

    An empty list means the message is structurally valid. Unknown-but-declared
    ``t`` values that are not yet implemented are NOT treated as errors (they are
    dropped silently at the dispatcher today, per main.handle_raw_frame); they are
    simply reported as ``unimplemented`` so callers can decide.

    This function never raises; malformed input yields a non-empty list.
    """
    errors: list[str] = []

    if not isinstance(data, dict):
        return ["message is not a JSON object"]
    if "t" not in data:
        return ['missing "t" field']

    t = data["t"]
    if not isinstance(t, str) or not t:
        return ['"t" must be a non-empty string']

    # Type-level checks for existing message kinds. Mirrors what main.handle_message
    # already requires to behave correctly; does not alter behaviour.
    if t == "click":
        if "btn" in data and not isinstance(data["btn"], str):
            errors.append('click.btn must be a string')
        if "n" in data and not isinstance(data["n"], (int, float)):
            errors.append("click.n must be a number")
    elif t in ("move", "scroll"):
        for field in ("dx", "dy"):
            if field in data and not isinstance(data[field], (int, float)):
                errors.append(f"{t}.{field} must be a number")
    elif t == "gesture":
        if not isinstance(data.get("name"), str):
            errors.append("gesture.name must be a string")
    elif t == "hotkey":
        keys = data.get("keys")
        if not isinstance(keys, list) or not keys or not all(
            isinstance(k, str) for k in keys
        ):
            errors.append("hotkey.keys must be a non-empty list of strings")
    elif t == "type":
        if not isinstance(data.get("text"), str):
            errors.append("type.text must be a string")
    elif t == "key":
        if not isinstance(data.get("name"), str) and not isinstance(
            data.get("key"), str
        ):
            errors.append("key.name/key must be a string")
    elif t == "deck":
        if data.get("id") is None:
            errors.append("deck.id is required")
    elif t == "laser":
        if "on" in data and not isinstance(data["on"], bool):
            errors.append("laser.on must be a boolean")

    return errors


def validate_json(raw: str) -> tuple[Any, list[str]]:
    """Parse a raw text frame; returns ``(data, problems)``.

    ``data`` is None if the payload is not valid JSON or not a JSON object. Only
    dict-shaped payloads are considered protocol messages (matches dispatcher).
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None, ["not valid JSON"]
    if isinstance(data, dict):
        return data, validate_message(data)
    return None, ["message is not a JSON object"]


def hello_payload() -> dict[str, Any]:
    """Extra fields merged into the host "hello" message for capability detection."""
    return {
        "protocol": PROTOCOL_VERSION,
        "features": HOST_FEATURES,
    }
