"""Standalone tests for the control API the Flutter host UI talks to.

Run:  python receiver/test_control_server.py

SAFETY: never touches the real clipboard (history is seeded directly) and never
opens a folder; only the pure payload builders are exercised.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import clipboard_sync  # noqa: E402
import control_server  # noqa: E402

_FAILURES = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _FAILURES
    if cond:
        print(f"ok   {name}")
    else:
        _FAILURES += 1
        print(f"FAIL {name} {detail}")


def main() -> int:
    folders = control_server._transfer_folders()
    check("folders has both sides", set(folders) == {"fromPhone", "fromPc"}, str(folders))
    check("folders are absolute", all(Path(p).is_absolute() for p in folders.values()))

    clipboard_sync._clear_history()
    clipboard_sync._add_history("una contraseña secreta", 1.5)
    history = control_server._clipboard_history()
    check("history reports the entry", len(history) == 1, str(history))
    check("history carries length", history[0]["len"] == len("una contraseña secreta"))
    check("history leaks no content", "text" not in history[0], str(history[0]))
    clipboard_sync._clear_history()

    # Bluetooth PAN and a second NIC are reachable on addresses local_ip() never
    # returns, so every usable one has to be advertised, preferred first.
    import main as core

    addresses = core.local_ips()
    check("at least one address", bool(addresses), str(addresses))
    check(
        "every address is labelled and typed",
        all({"label", "ip", "kind"} <= set(a) for a in addresses),
        str(addresses),
    )
    check(
        "no loopback or unconfigured address",
        not any(
            a["ip"].startswith("127.") or a["ip"].startswith("169.254.")
            for a in addresses
        ),
        str(addresses),
    )
    check(
        "preferred address comes first",
        addresses[0]["ip"] == core.local_ip() or len(addresses) == 1,
        f'{addresses[0]["ip"]} vs {core.local_ip()}',
    )
    kinds = {a["kind"] for a in addresses}
    check("kinds are known", kinds <= {"bluetooth", "wifi", "ethernet", "other"}, str(kinds))
    check(
        "a bluetooth link sorts above the rest",
        [a["kind"] for a in addresses[1:]].count("bluetooth") == 0
        or [a["kind"] for a in addresses[1:]][0] == "bluetooth",
        str([a["kind"] for a in addresses]),
    )

    snap = control_server._connect_info()
    check("connect info advertises addresses", bool(snap.get("addresses")), str(snap.get("addresses")))

    snap = control_server._status_snapshot()
    check("snapshot carries folders", "folders" in snap)
    features = snap.get("features") or {}
    check("snapshot carries the protocol version", bool(features.get("protocol")), str(features))
    check("snapshot carries the domains", features.get("domains", {}).get("clipboard") is True)

    print(f"\n{_FAILURES} failure(s)")
    return 1 if _FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
