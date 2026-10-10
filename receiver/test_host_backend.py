"""Standalone test: the HostController hooks keep the reply-capable protocol.

Run:  python receiver/test_host_backend.py

gui_app and control_server share one HostController (host_backend). Its hooks wrap
core.handle_message / core.handle_raw_frame, so they must pass the websocket through
and return the reply dict -- otherwise status/action/media/app_volume/windows/
clipboard/file answer nothing when the Flutter UI drives the host.
"""

from __future__ import annotations

import queue
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import main as core  # noqa: E402
from host_backend import HostController  # noqa: E402

_FAILURES = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _FAILURES
    if cond:
        print(f"ok   {name}")
    else:
        _FAILURES += 1
        print(f"FAIL {name} {detail}")


def main() -> int:
    seen: list[tuple[dict, object]] = []
    core.handle_message = lambda data, websocket=None: (  # type: ignore[assignment]
        seen.append((data, websocket)) or {"t": "status", "ok": True}
    )
    core.handle_raw_frame = lambda raw, websocket=None: seen.append((raw, websocket))  # type: ignore[assignment]

    HostController(queue.SimpleQueue())._install_hooks()

    ws = object()
    reply = core.handle_message({"t": "status"}, ws)
    check("handle_message returns the reply", reply == {"t": "status", "ok": True}, str(reply))
    check("handle_message forwards the websocket", seen[-1][1] is ws)

    core.handle_raw_frame(b"\x00" * 8, ws)
    check("handle_raw_frame forwards the websocket", seen[-1][1] is ws)

    # gui_app logs the new domains but must not swallow the reply.
    reply = core.handle_message({"t": "clipboard", "action": "get"}, ws)
    check("new domains still reply", reply == {"t": "status", "ok": True}, str(reply))

    print(f"\n{_FAILURES} failure(s)")
    return 1 if _FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
