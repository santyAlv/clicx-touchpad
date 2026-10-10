"""Shared host lifecycle: WS/UDP server control + adb helpers.

Extracted from gui_app.py so both the Tkinter GUI and the headless
control_server (used by the Flutter UI) can drive the same server
without duplicating it.
"""

from __future__ import annotations

import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import main as core


def find_adb() -> str | None:
    """Locate adb.exe on PATH or common Android SDK locations."""
    which = shutil.which("adb")
    if which:
        return which
    candidates: list[Path] = []
    for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = os.environ.get(env)
        if root:
            candidates.append(Path(root) / "platform-tools" / "adb.exe")
    local = (
        Path.home()
        / "AppData"
        / "Local"
        / "Android"
        / "Sdk"
        / "platform-tools"
        / "adb.exe"
    )
    candidates.append(local)
    for p in candidates:
        if p.is_file():
            return str(p)
    return None


def run_adb(args: list[str], timeout: float = 12.0) -> tuple[int, str]:
    adb = find_adb()
    if not adb:
        return 1, "adb no encontrado. Instalá platform-tools o agregá adb al PATH."
    try:
        proc = subprocess.run(
            [adb, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        msg = out if out else err
        return proc.returncode, msg or f"exit {proc.returncode}"
    except subprocess.TimeoutExpired:
        return 1, "adb timeout"
    except OSError as e:
        return 1, str(e)


class HostController:
    """Runs WS + UDP in background threads; pushes UI events on a queue."""

    def __init__(self, ui_q: "queue.SimpleQueue[tuple[str, Any]]") -> None:
        self.ui_q = ui_q
        self.port = core.PORT
        self._ws_thread: threading.Thread | None = None
        self._udp_thread: threading.Thread | None = None
        self._server: Any = None
        self._udp_sock: socket.socket | None = None
        self._running = False
        self._clients = 0
        self._lock = threading.Lock()

    def log(self, msg: str) -> None:
        self.ui_q.put(("log", msg))

    def set_status(self, text: str, kind: str = "idle") -> None:
        self.ui_q.put(("status", (text, kind)))

    def set_clients(self, n: int) -> None:
        self.ui_q.put(("clients", n))

    def is_running(self) -> bool:
        return self._running

    def start(self, port: int) -> None:
        with self._lock:
            if self._running:
                return
            self.port = port
            self._running = True

        core._boost_timer_resolution()
        core._boost_thread_priority()
        core.ensure_firewall_rules(self.port, core.UDP_PORT)
        self._install_hooks()

        self._udp_thread = threading.Thread(
            target=self._run_udp, name="clicx-udp", daemon=True
        )
        self._udp_thread.start()

        self._ws_thread = threading.Thread(
            target=self._run_ws, name="clicx-ws", daemon=True
        )
        self._ws_thread.start()

        if not any(t.name == "clicx-laser" for t in threading.enumerate()):
            threading.Thread(
                target=core.laser_overlay_worker, name="clicx-laser", daemon=True
            ).start()

        ip = core.local_ip()
        self.set_status("Listening", "ok")
        self.log(f"Host activo — ws://{ip}:{self.port}")
        self.log(f"UDP moves — {ip}:{core.UDP_PORT}")

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False

        srv = self._server
        self._server = None
        if srv is not None:
            try:
                srv.shutdown()
            except Exception:  # noqa: BLE001
                try:
                    srv.close()
                except Exception:  # noqa: BLE001
                    pass

        sock = self._udp_sock
        self._udp_sock = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

        self._clients = 0
        self.set_clients(0)
        self.set_status("Stopped", "idle")
        self.log("Host detenido")

    def _install_hooks(self) -> None:
        if getattr(self, "_hooks_ready", False):
            return
        self._hooks_ready = True
        controller = self

        def ws_handler(websocket: Any) -> None:
            core._boost_thread_priority()
            core.enable_tcp_nodelay_ws(websocket)
            core.register_client(websocket)
            peer = None
            try:
                peer = websocket.remote_address
            except Exception:  # noqa: BLE001
                pass
            controller._clients += 1
            controller.set_clients(controller._clients)
            controller.set_status("Connected", "ok")
            controller.log(f"Cliente conectado: {peer}")
            try:
                import json

                websocket.send(
                    json.dumps(
                        {
                            "t": "hello",
                            "name": "ClicX",
                            "version": core.VERSION,
                            "deck": __import__("deck_store").deck_for_client(),
                            **__import__("protocol").hello_payload(),
                        }
                    )
                )
            except Exception:  # noqa: BLE001
                core.unregister_client(websocket)
                return
            try:
                for raw in websocket:
                    core.handle_raw_frame(raw, websocket)
            except Exception:  # noqa: BLE001
                pass
            finally:
                core.unregister_client(websocket)
                # Same per-connection teardown main.py does: open file handles,
                # partial uploads and clipboard auto-sync all key off the socket.
                for module in ("file_transfer", "clipboard_sync"):
                    try:
                        __import__(module).cleanup_connection(websocket)
                    except Exception:  # noqa: BLE001
                        pass
                core.decay_velocity()
                controller._clients = max(0, controller._clients - 1)
                controller.set_clients(controller._clients)
                if controller._clients == 0 and controller._running:
                    controller.set_status("Listening", "ok")
                controller.log(f"Cliente desconectado: {peer}")

        self._ws_handler = ws_handler

        orig_handle = core.handle_message

        def handle_message(data: dict[str, Any], websocket: Any = None) -> dict | None:
            t = data.get("t")
            if t == "click":
                controller.log(
                    f"Click {data.get('btn', 'left')} x{data.get('n', 1)}"
                )
            elif t == "gesture":
                controller.log(f"Gesto {data.get('name')}")
            elif t == "zoom":
                controller.log("Zoom")
            elif t == "laser":
                controller.log(
                    f"Láser {'ON' if data.get('on') else 'OFF'} {data.get('color', '')}"
                )
            elif t == "volume":
                controller.log(
                    f"Volumen {data.get('action', 'set')} {data.get('level', '')}"
                )
            elif t == "type":
                txt = str(data.get("text", ""))
                controller.log(f"Type {len(txt)} chars")
            elif t == "key":
                controller.log(f"Key {data.get('name') or data.get('key')}")
            elif t == "deck":
                controller.log(f"Deck {data.get('id')}")
            elif t in ("status", "action", "media", "app_volume", "windows", "clipboard", "file"):
                controller.log(f"{t} → {data.get('action', data.get('get', ''))}")
            return orig_handle(data, websocket)

        core.handle_message = handle_message  # type: ignore[assignment]

        orig_raw = core.handle_raw_frame

        def handle_raw_frame(raw: Any, websocket: Any = None) -> None:
            if isinstance(raw, str) and raw.startswith("c,"):
                controller.log(f"Click {raw}")
            orig_raw(raw, websocket)

        core.handle_raw_frame = handle_raw_frame  # type: ignore[assignment]

    def _run_ws(self) -> None:
        from websockets.sync.server import serve as sync_serve

        try:
            with sync_serve(
                self._ws_handler,
                "0.0.0.0",
                self.port,
                compression=None,
                max_size=2**16,
                ping_interval=60,
                ping_timeout=60,
            ) as server:
                self._server = server
                server.serve_forever()
        except OSError as e:
            self.log(f"Error WebSocket: {e}")
            self.set_status("Port error", "err")
            self._running = False
        except Exception as e:  # noqa: BLE001
            if self._running:
                self.log(f"WebSocket cerrado: {e}")
        finally:
            self._server = None
            if self._running:
                self._running = False
                self.set_status("Stopped", "idle")

    def _run_udp(self) -> None:
        import struct

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._udp_sock = sock
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
            sock.bind(("0.0.0.0", core.UDP_PORT))
            sock.settimeout(0.5)
            while self._running:
                try:
                    data, _addr = sock.recvfrom(64)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if len(data) == 8:
                    dx, dy = struct.unpack("<ff", data)
                    core.apply_move(dx, dy)
        except OSError as e:
            self.log(f"UDP no disponible: {e}")
        finally:
            try:
                sock.close()
            except OSError:
                pass
            self._udp_sock = None
