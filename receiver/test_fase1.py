"""Standalone tests for Fase 1 host modules (status/actions/media/app_volume/windows).

Run:  python receiver/test_fase1.py   (with receiver deps installed in the venv)

SAFETY: never executes shutdown/restart/logout/lock/sleep. Side-effectful helpers are
monkeypatched to no-ops so no real OS action (media key, Win+D, screenshot) occurs.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

_FAILURES = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _FAILURES
    if not cond:
        _FAILURES += 1
        print(f"FAIL {name}  {detail}")
    else:
        print(f"ok   {name}")


# ---------------------------------------------------------------------------
# actions
# ---------------------------------------------------------------------------
def test_actions():
    import actions

    # Unknown action rejected (no side effects).
    r = actions.handle_action({"t": "action", "name": "nope"})
    check("unknown action denied", r["ok"] is False)

    # Dangerous requires prepare then confirm.
    guard = actions.ActionGuard()
    t0 = 1_000_000.0
    r = actions.handle_action(
        {"t": "action", "name": "shutdown"}, guard=guard, now=t0
    )
    check(
        "dangerous without confirm denied",
        r["ok"] is False and r["phase"] == "need-prepare",
    )

    r = actions.handle_action(
        {"t": "action", "name": "shutdown", "confirm": "prepare"},
        guard=guard,
        now=t0,
    )
    check("prepare arms", r["phase"] == "armed" and r["ok"] is False)
    check("guard is armed", guard.is_armed("shutdown", t0) is True)

    # Confirm "go" WITHOUT patching would execute shutdown — so patch impl to no-op.
    acted = {"ran": False}

    def fake_run(name):
        acted["ran"] = True
        return True

    orig = actions._run_impl
    actions._run_impl = fake_run
    try:
        r = actions.handle_action(
            {"t": "action", "name": "shutdown", "confirm": "go"},
            guard=guard,
            now=t0,
        )
    finally:
        actions._run_impl = orig
    check("confirm within window runs (patched)", r["ok"] is True and acted["ran"] is True)

    # Timeout expiry: arm at t0, confirm later than window.
    guard = actions.ActionGuard()
    actions.handle_action(
        {"t": "action", "name": "restart", "confirm": "prepare"}, guard=guard, now=t0
    )
    r = actions.handle_action(
        {"t": "action", "name": "restart", "confirm": "go"},
        guard=guard,
        now=t0 + actions.CONFIRM_WINDOW_S + 1,
    )
    check("expired confirm denied", r["ok"] is False and r["phase"] == "expired")

    # Safe action runs immediately.
    acted = {"ran": False}

    def fake_safe(name):
        acted["ran"] = True
        return True

    actions._run_impl = fake_safe
    try:
        r = actions.handle_action({"t": "action", "name": "desktop"})
    finally:
        actions._run_impl = orig
    check("safe action runs immediately", r["ok"] is True and acted["ran"] is True)


# ---------------------------------------------------------------------------
# media
# ---------------------------------------------------------------------------
def test_media():
    import media

    orig = media._tap
    media._tap = lambda vk: None
    try:
        r = media.handle_media({"t": "media", "action": "play_pause"})
        check("play_pause ok", r["ok"] is True and r["action"] == "play_pause")
        r = media.handle_media({"t": "media", "action": "next"})
        check("next ok", r["ok"] is True)
        r = media.handle_media({"t": "media", "action": "bogus"})
        check("unknown media denied", r["ok"] is False)
        r = media.handle_media({"t": "media", "action": "mute"})
        check("volume routed to t:volume", r["ok"] is False and "t:volume" in r["error"])
    finally:
        media._tap = orig


# ---------------------------------------------------------------------------
# app_volume
# ---------------------------------------------------------------------------
def test_app_volume():
    import app_volume

    r = app_volume.handle_app_volume({"t": "app_volume", "action": "list"})
    check("list returns apps array", r["t"] == "app_volume" and isinstance(r["apps"], list))

    r = app_volume.handle_app_volume({"t": "app_volume", "action": "unknown"})
    check("unknown app_volume denied", r["ok"] is False)

    # set on a nonexistent id → side-effect-free error.
    r = app_volume.handle_app_volume(
        {"t": "app_volume", "action": "set", "id": 999999999, "volume": 50}
    )
    check("set missing session denied", r["ok"] is False)

    r = app_volume.handle_app_volume({"t": "app_volume", "action": "set", "id": "x", "volume": 50})
    check("bad id denied", r["ok"] is False)


# ---------------------------------------------------------------------------
# window_manager
# ---------------------------------------------------------------------------
def test_windows():
    import window_manager

    lr = window_manager.list_windows()
    check("list returns windows array", lr["t"] == "windows" and isinstance(lr["windows"], list))
    win_list = lr["windows"]

    r = window_manager.handle_windows({"t": "windows", "action": "unknown"})
    check("unknown windows action denied", r["ok"] is False)

    # focus a nonexistent id → side-effect-free error.
    r = window_manager.handle_windows(
        {"t": "windows", "action": "focus", "id": 999999999}
    )
    check("focus missing window denied", r["ok"] is False)

    # Window entries carry the safe shape only (id, title, app, active, minimized).
    check("window entries carry safe shape", all(
        set(w) >= {"id", "title", "app", "active", "minimized"}
        for w in win_list
    ))
    check("no extra sensitive keys exposed", all(
        set(w) <= {"id", "title", "app", "active", "minimized"}
        for w in win_list
    ))


# ---------------------------------------------------------------------------
# system_status
# ---------------------------------------------------------------------------
def test_status():
    import system_status

    s = system_status.collect_status(version="0.8.0", ip="127.0.0.1")
    for key in ("device", "connected", "cpu", "ram", "disk", "ip", "version"):
        check(f"status has {key}", key in s)
    check("connected true", s["connected"] is True)


def check_cpu_sampling() -> None:
    """CPU load must be the average since the last poll, not a 0.1 s window.

    interval=0.1 answered 0-1% while Task Manager showed ten times as much, and
    it blocked the caller for 100 ms on every status request.
    """
    import time

    import system_status as st

    st._cpu_primed = False
    first = st._cpu()
    check(
        "first cpu reading primes the counter",
        first is not None and first["percent"] is None,
        str(first),
    )

    t0 = time.perf_counter()
    st._cpu()
    elapsed = (time.perf_counter() - t0) * 1000
    check("cpu sampling does not block", elapsed < 50, f"{elapsed:.1f} ms")

    time.sleep(0.4)
    reading = st._cpu()
    percent = (reading or {}).get("percent")
    check(
        "cpu percent is a real reading",
        isinstance(percent, float) and 0.0 <= percent <= 100.0,
        str(reading),
    )


def main() -> int:
    test_actions()
    test_media()
    test_app_volume()
    test_windows()
    test_status()
    check_cpu_sampling()

    print("\n---")
    print(f"{_FAILURES} failure(s)")
    return 1 if _FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
