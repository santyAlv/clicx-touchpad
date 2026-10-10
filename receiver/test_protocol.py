"""Standalone tests for receiver/protocol.py (Fase 0).

Run:  python receiver/test_protocol.py
Exits 0 on success, prints failures otherwise. No third-party deps.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import protocol  # noqa: E402

_FAILURES = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _FAILURES
    if not cond:
        _FAILURES += 1
        print(f"FAIL {name}  {detail}")
    else:
        print(f"ok   {name}")


def test_version():
    check("PROTOCOL_VERSION defined", protocol.PROTOCOL_VERSION == "0.8")


def test_validate_shape():
    check("non-object rejected", protocol.validate_message(["x"]) == ["message is not a JSON object"], str(protocol.validate_message(["x"])))
    check("missing t rejected", protocol.validate_message({"a": 1}) == ['missing "t" field'])
    check("empty t rejected", '"t" must be a non-empty string' in protocol.validate_message({"t": ""}))
    check("non-string t rejected", '"t" must be a non-empty string' in protocol.validate_message({"t": 5}))


def test_existing_types_valid():
    cases = [
        {"t": "click", "btn": "left", "n": 1},
        {"t": "move", "dx": 1, "dy": -2.5},
        {"t": "gesture", "name": "swipe3_right"},
        {"t": "hotkey", "keys": ["ctrl", "c"]},
        {"t": "type", "text": "hola"},
        {"t": "key", "name": "enter"},
        {"t": "deck", "id": "b1"},
        {"t": "laser", "on": True, "color": "red"},
    ]
    for c in cases:
        check(f"valid {c['t']}", protocol.validate_message(c) == [], str(protocol.validate_message(c)))


def test_existing_types_invalid():
    check("bad click.n", "click.n must be a number" in protocol.validate_message({"t": "click", "n": "x"}))
    check("bad move.dx", "move.dx must be a number" in protocol.validate_message({"t": "move", "dx": "a"}))
    check("bad gesture.name", "gesture.name must be a string" in protocol.validate_message({"t": "gesture"}))
    check("bad hotkey.keys", "hotkey.keys must be a non-empty list of strings" in protocol.validate_message({"t": "hotkey", "keys": "c"}))
    check("bad type.text", "type.text must be a string" in protocol.validate_message({"t": "type"}))
    check("bad laser.on", "laser.on must be a boolean" in protocol.validate_message({"t": "laser", "on": 1}))


def test_known_and_planned():
    for t in ("move", "click", "deck", "status", "windows", "app_volume", "hello"):
        check(f"known_type {t}", protocol.known_type(t) is True)
    check("known_type nonsense false", protocol.known_type("zzz") is False)
    check("is_planned windows", protocol.is_planned_type("windows") is True)
    check("is_planned move false", protocol.is_planned_type("move") is False)


def test_validate_json():
    data, errs = protocol.validate_json('{"t":"click","btn":"left","n":1}')
    check("json ok", errs == [] and isinstance(data, dict))
    data, errs = protocol.validate_json("not json")
    check("json invalid", data is None and "not valid JSON" in errs)
    _, errs = protocol.validate_json("[1,2]")
    check("json non-object", "message is not a JSON object" in errs)


def test_hello_and_features():
    h = protocol.hello_payload()
    check("hello has protocol", h["protocol"] == "0.8")
    check("hello has features", "features" in h)
    check("features has domains", "domains" in h["features"])
    d = h["features"]["domains"]
    # Enabled in Fase 1:
    for dom in ("windows", "app_volume", "status", "actions", "media"):
        check(f"{dom} enabled", d[dom] is True)
    # Enabled in Fase 2 (integración):
    for dom in ("clipboard", "file"):
        check(f"{dom} enabled", d[dom] is True)
    # Not yet implemented (later phases):
    for dom in ("screen", "scenes", "profiles", "auth"):
        check(f"{dom} not enabled yet", d[dom] is False)


def main() -> int:
    test_version()
    test_validate_shape()
    test_existing_types_valid()
    test_existing_types_invalid()
    test_known_and_planned()
    test_validate_json()
    test_hello_and_features()
    print("\n---")
    print(f"{_FAILURES} failure(s)")
    return 1 if _FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
