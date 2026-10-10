"""Headless control API for the ClicX host — used by the Flutter desktop UI.

Runs the real WS/UDP input server via HostController (same code path as
gui_app.py), plus a local-only control WebSocket on 127.0.0.1:CONTROL_PORT
that a UI client (Flutter) talks JSON to: status, deck CRUD, USB pairing,
QR/connect info. No Tkinter involved — this replaces gui_app.py as the
process the .exe launches when a native UI drives it instead.
"""

from __future__ import annotations

import base64
import io
import json
import os
import queue
import subprocess
import sys
import threading
from typing import Any

import deck_store
import main as core
from host_backend import HostController, run_adb

CONTROL_PORT = 51236

_ui_q: "queue.SimpleQueue[tuple[str, Any]]" = queue.SimpleQueue()
_controller = HostController(_ui_q)
_usb_active = False

_clients_lock = threading.Lock()
_control_clients: set[Any] = set()


def _send(ws: Any, obj: dict[str, Any]) -> None:
    try:
        ws.send(json.dumps(obj))
    except Exception:  # noqa: BLE001
        pass


def _broadcast(obj: dict[str, Any]) -> None:
    with _clients_lock:
        clients = list(_control_clients)
    for ws in clients:
        _send(ws, obj)


def _pump_events() -> None:
    """Forward HostController log/status/clients events to control clients."""
    while True:
        kind, payload = _ui_q.get()
        if kind == "log":
            _broadcast({"t": "log", "msg": str(payload)})
        elif kind == "status":
            text, sk = payload
            _broadcast({"t": "hostStatus", "text": text, "kind": sk})
        elif kind == "clients":
            _broadcast({"t": "clients", "n": int(payload)})


def _connect_info() -> dict[str, Any]:
    ip = core.local_ip()
    port = _controller.port
    return {
        "t": "connectInfo",
        "ip": ip,
        "port": port,
        "url": f"ws://{ip}:{port}",
        "payload": f"clicx://connect?host={ip}&port={port}",
        "version": core.VERSION,
        # Every link the phone could reach us on. Over Bluetooth PAN or a second
        # NIC the default-route address above is the wrong one, so the UI lets
        # the user pick and builds the QR from the choice.
        "addresses": core.local_ips(),
    }


def _transfer_folders() -> dict[str, str]:
    """Paths the phone drops files into / picks them up from."""
    from file_transfer import transfer_dir

    return {
        "fromPhone": str(transfer_dir("from_phone")),
        "fromPc": str(transfer_dir("from_pc")),
    }


def _open_folder(ws: Any, which: str) -> None:
    from pathlib import Path

    folders = _transfer_folders()
    path = folders.get("fromPc" if which == "fromPc" else "fromPhone")
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        os.startfile(path)  # noqa: S606
    except Exception as e:  # noqa: BLE001
        _send(ws, {"t": "folderError", "msg": str(e)})


def _clipboard_history() -> list[dict[str, Any]]:
    """History metadata only — clipboard_sync never exposes content to the log/UI."""
    from clipboard_sync import handle_clipboard

    reply = handle_clipboard({"action": "history"}) or {}
    return [
        {"ts": item.get("ts"), "len": item.get("len")}
        for item in reply.get("items", [])
    ]


def _status_snapshot() -> dict[str, Any]:
    from protocol import HOST_FEATURES

    return {
        "t": "status",
        "folders": _transfer_folders(),
        "features": HOST_FEATURES,
        "running": _controller.is_running(),
        "clients": _controller._clients,
        "usb": _usb_active,
        **{k: v for k, v in _connect_info().items() if k != "t"},
    }


def _usb_on(ws: Any) -> None:
    global _usb_active
    port = _controller.port
    code, msg = run_adb(["devices"])
    if code != 0:
        _send(ws, {"t": "usb", "active": False, "error": msg})
        return
    if "device" not in msg.replace("List of devices", ""):
        _send(
            ws,
            {
                "t": "usb",
                "active": False,
                "error": "No adb device found. Enable USB debugging and reconnect the cable.",
            },
        )
        return
    code, msg = run_adb(["reverse", f"tcp:{port}", f"tcp:{port}"])
    if code != 0:
        _send(ws, {"t": "usb", "active": False, "error": msg})
        return
    _usb_active = True
    _send(ws, {"t": "usb", "active": True})


def _usb_off(ws: Any) -> None:
    global _usb_active
    port = _controller.port
    code, msg = run_adb(["reverse", "--remove", f"tcp:{port}"])
    _usb_active = False
    _send(ws, {"t": "usb", "active": False, "error": None if code == 0 else msg})


def _list_apps(ws: Any, query: str, limit: int = 40) -> None:
    from icon_extract import extract_icon_b64
    from windows_apps import search_apps

    apps = []
    for app in search_apps(query)[:limit]:
        try:
            icon = extract_icon_b64(app["path"])
        except Exception:  # noqa: BLE001
            icon = None
        apps.append({"name": app["name"], "path": app["path"], "iconB64": icon})
    _send(ws, {"t": "apps", "apps": apps})


def _pick_image(ws: Any) -> None:
    """Native file dialog on the Python side, so the UI needs no plugin."""
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$d = New-Object System.Windows.Forms.OpenFileDialog; "
        "$d.Filter = 'Imagenes|*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.ico'; "
        "if ($d.ShowDialog() -eq 'OK') { $d.FileName }"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", script],
            capture_output=True,
            text=True,
            timeout=180,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:  # noqa: BLE001
        _send(ws, {"t": "pickedImage", "iconB64": None, "error": str(e)})
        return

    path = (out.stdout or "").strip()
    if not path:
        _send(ws, {"t": "pickedImage", "iconB64": None})
        return

    try:
        from PIL import Image

        img = Image.open(path).convert("RGBA")
        img.thumbnail((128, 128), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        icon = base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as e:  # noqa: BLE001
        _send(ws, {"t": "pickedImage", "iconB64": None, "error": str(e)})
        return

    _send(ws, {"t": "pickedImage", "iconB64": icon})


def _add_button(button: Any, page_id: Any) -> None:
    """Append a button and persist immediately.

    The add dialog runs in its own process, so it has no shared in-memory deck
    to mutate — it hands the button here and every window is told the result.
    """
    if not isinstance(button, dict):
        return
    cfg = deck_store.load_config()
    pages = cfg.get("pages") or []
    if not pages:
        return
    page = pages[0]
    if page_id:
        for candidate in pages:
            if str(candidate.get("id")) == str(page_id):
                page = candidate
                break
    page.setdefault("buttons", []).append(button)
    deck_store.save_config(cfg)
    _broadcast({"t": "deck", "deck": deck_store.deck_for_client()})


def _handle(ws: Any, data: dict[str, Any]) -> None:
    t = data.get("t")
    if t == "getStatus":
        _send(ws, _status_snapshot())
    elif t == "start":
        port = int(data.get("port") or core.PORT)
        _controller.start(port)
        _send(ws, _status_snapshot())
    elif t == "stop":
        _controller.stop()
        _send(ws, _status_snapshot())
    elif t == "getConnectInfo":
        _send(ws, _connect_info())
    elif t == "getDeck":
        _send(ws, {"t": "deck", "deck": deck_store.deck_for_client()})
    elif t == "saveDeck":
        deck = data.get("deck")
        if isinstance(deck, dict):
            deck_store.save_config(deck)
            _broadcast({"t": "deck", "deck": deck_store.deck_for_client()})
    elif t == "addButton":
        _add_button(data.get("button"), data.get("pageId"))
    elif t == "testButton":
        bid = data.get("id")
        if bid:
            deck_store.execute_button(str(bid))
    elif t == "usbOn":
        _usb_on(ws)
    elif t == "usbOff":
        _usb_off(ws)
    elif t == "setAccent":
        color = str(data.get("color", "")).strip()
        if color:
            # save_config broadcasts deckSync to the phones, which carry the
            # accent in the same payload.
            deck_store.set_accent(color)
            _broadcast({"t": "deck", "deck": deck_store.deck_for_client()})
    elif t == "listApps":
        _list_apps(ws, str(data.get("q", "")))
    elif t == "pickImage":
        _pick_image(ws)
    elif t == "openFolder":
        _open_folder(ws, str(data.get("folder", "fromPhone")))
    elif t == "getClipboardHistory":
        _send(ws, {"t": "clipboardHistory", "items": _clipboard_history()})
    elif t == "clearClipboardHistory":
        from clipboard_sync import handle_clipboard

        handle_clipboard({"action": "clear"})
        _broadcast({"t": "clipboardHistory", "items": []})


def _control_handler(ws: Any) -> None:
    with _clients_lock:
        _control_clients.add(ws)
    _send(ws, _status_snapshot())
    try:
        for raw in ws:
            try:
                data = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if isinstance(data, dict):
                _handle(ws, data)
    except Exception:  # noqa: BLE001
        pass
    finally:
        with _clients_lock:
            _control_clients.discard(ws)


def run() -> None:
    from websockets.sync.server import serve as sync_serve

    core.ensure_elevated(interactive=True)
    core._boost_timer_resolution()
    core._boost_thread_priority()

    threading.Thread(target=_pump_events, name="clicx-control-pump", daemon=True).start()
    _controller.start(core.PORT)

    print(f"ClicX control API — ws://127.0.0.1:{CONTROL_PORT}", flush=True)
    with sync_serve(
        _control_handler,
        "127.0.0.1",
        CONTROL_PORT,
        compression=None,
    ) as server:
        server.serve_forever()


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        sys.exit(0)
