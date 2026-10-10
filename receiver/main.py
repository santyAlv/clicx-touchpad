"""ClicX host — minimum-latency Windows cursor bridge (sync WS + optional UDP)."""

from __future__ import annotations

import ctypes
import json
import os
import queue
import socket
import struct
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from typing import Any

# Windowed .exe: no console — avoid print crashes
if getattr(sys, "frozen", False):
    try:
        if sys.stdout is None or not hasattr(sys.stdout, "write"):
            sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
        if sys.stderr is None or not hasattr(sys.stderr, "write"):
            sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    except Exception:  # noqa: BLE001
        pass

from pynput.keyboard import Controller as KeyboardController
from pynput.keyboard import Key
from pynput.mouse import Button, Controller as MouseController
from websockets.sync.server import serve as sync_serve

PORT = 51234
UDP_PORT = 51235
VERSION = "0.8.0"

# Compensate perceived Wi‑Fi lag (ms). 0 = off. Keep low — high values feel jumpy on fast flicks.
PRED_MS = float(os.environ.get("CLICX_PRED_MS", "3"))
# Cap predicted velocity (px/ms) so a spike never launches the cursor.
_PRED_V_MAX = float(os.environ.get("CLICX_PRED_V_MAX", "4.5"))

# --- Win32 SendInput ---
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x01000
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
WHEEL_DELTA = 120
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
THREAD_PRIORITY_TIME_CRITICAL = 15
THREAD_PRIORITY_HIGHEST = 2

_CLICK_FLAGS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = (("mi", MOUSEINPUT), ("ki", KEYBDINPUT))

    _anonymous_ = ("u",)
    _fields_ = (("type", wintypes.DWORD), ("u", _U))


_SendInput = ctypes.windll.user32.SendInput
_SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
_SendInput.restype = wintypes.UINT

_frac_x = 0.0
_frac_y = 0.0
_vx = 0.0  # px per ms (EMA)
_vy = 0.0
_last_t = 0.0
_scroll_acc_x = 0.0
_scroll_acc_y = 0.0
_input = INPUT(type=INPUT_MOUSE)
_input.mi.dwFlags = MOUSEEVENTF_MOVE
_move_lock = threading.Lock()
_scroll_lock = threading.Lock()
_clients_lock = threading.Lock()
_clients: set[Any] = set()
_type_lock = threading.Lock()


def register_client(ws: Any) -> None:
    with _clients_lock:
        _clients.add(ws)


def unregister_client(ws: Any) -> None:
    with _clients_lock:
        _clients.discard(ws)


def broadcast_json(payload: dict[str, Any]) -> None:
    raw = json.dumps(payload)
    dead: list[Any] = []
    with _clients_lock:
        for ws in _clients:
            try:
                ws.send(raw)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            _clients.discard(ws)


class GUITHREADINFO(ctypes.Structure):
    _fields_ = (
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    )


_EDITABLE_CLASS_FRAGMENTS = (
    "edit",
    "richedit",
    "textinput",
    "textarea",
    "passwordbox",
    "autofill",
)


def is_focus_editable() -> bool:
    """Best-effort: caret present or classic Win32 edit class."""
    try:
        info = GUITHREADINFO()
        info.cbSize = ctypes.sizeof(GUITHREADINFO)
        if not ctypes.windll.user32.GetGUIThreadInfo(0, ctypes.byref(info)):
            return False
        if info.hwndCaret:
            return True
        hwnd = info.hwndFocus
        if not hwnd:
            return False
        buf = ctypes.create_unicode_buffer(256)
        ctypes.windll.user32.GetClassNameW(hwnd, buf, 256)
        cls = buf.value.lower()
        return any(frag in cls for frag in _EDITABLE_CLASS_FRAGMENTS)
    except Exception:  # noqa: BLE001
        return False


def schedule_editable_notify(*, delay: float = 0.12) -> None:
    def work() -> None:
        time.sleep(delay)
        try:
            on = is_focus_editable()
            broadcast_json({"t": "editable", "on": on})
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=work, name="clicx-editable", daemon=True).start()


def _send_vk(vk: int) -> None:
    down = INPUT(type=INPUT_KEYBOARD)
    down.ki.wVk = vk
    down.ki.wScan = 0
    down.ki.dwFlags = 0
    down.ki.time = 0
    down.ki.dwExtraInfo = 0
    up = INPUT(type=INPUT_KEYBOARD)
    up.ki.wVk = vk
    up.ki.wScan = 0
    up.ki.dwFlags = KEYEVENTF_KEYUP
    up.ki.time = 0
    up.ki.dwExtraInfo = 0
    arr = (INPUT * 2)(down, up)
    _SendInput(2, arr, ctypes.sizeof(INPUT))


def _send_unicode_char(ch: str) -> None:
    code = ord(ch)
    if code > 0xFFFF:
        # Basic BMP only for SendInput unicode; skip astral for now
        return
    down = INPUT(type=INPUT_KEYBOARD)
    down.ki.wVk = 0
    down.ki.wScan = code
    down.ki.dwFlags = KEYEVENTF_UNICODE
    down.ki.time = 0
    down.ki.dwExtraInfo = 0
    up = INPUT(type=INPUT_KEYBOARD)
    up.ki.wVk = 0
    up.ki.wScan = code
    up.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP
    up.ki.time = 0
    up.ki.dwExtraInfo = 0
    arr = (INPUT * 2)(down, up)
    _SendInput(2, arr, ctypes.sizeof(INPUT))


def _clipboard_paste(text: str) -> bool:
    """Put text on clipboard and Ctrl+V into the focused control."""
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        payload = text.encode("utf-16-le") + b"\x00\x00"
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(payload))
        if not h_mem:
            return False
        ptr = kernel32.GlobalLock(h_mem)
        if not ptr:
            kernel32.GlobalFree(h_mem)
            return False
        ctypes.memmove(ptr, payload, len(payload))
        kernel32.GlobalUnlock(h_mem)
        if not user32.SetClipboardData(CF_UNICODETEXT, h_mem):
            kernel32.GlobalFree(h_mem)
            return False
    finally:
        user32.CloseClipboard()

    # Ctrl down, V down/up, Ctrl up
    VK_CONTROL, VK_V = 0x11, 0x56
    ctrl_down = INPUT(type=INPUT_KEYBOARD)
    ctrl_down.ki.wVk = VK_CONTROL
    v_down = INPUT(type=INPUT_KEYBOARD)
    v_down.ki.wVk = VK_V
    v_up = INPUT(type=INPUT_KEYBOARD)
    v_up.ki.wVk = VK_V
    v_up.ki.dwFlags = KEYEVENTF_KEYUP
    ctrl_up = INPUT(type=INPUT_KEYBOARD)
    ctrl_up.ki.wVk = VK_CONTROL
    ctrl_up.ki.dwFlags = KEYEVENTF_KEYUP
    arr = (INPUT * 4)(ctrl_down, v_down, v_up, ctrl_up)
    _SendInput(4, arr, ctypes.sizeof(INPUT))
    return True


def type_text(text: str) -> None:
    """Inject unicode text into the focused control (SendInput / paste)."""
    if not text:
        return
    with _type_lock:
        try:
            # Voice / multi-char: paste is far more reliable than per-key unicode
            if len(text) >= 2 and _clipboard_paste(text):
                print(f"[type] paste {len(text)!r}", flush=True)
                return
            for ch in text:
                if ch in ("\n", "\r"):
                    _send_vk(0x0D)  # Enter
                elif ch == "\t":
                    _send_vk(0x09)
                elif ch == "\b":
                    _send_vk(0x08)
                else:
                    _send_unicode_char(ch)
            print(f"[type] unicode {len(text)} chars", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[type] fail: {e}", flush=True)
            try:
                keyboard.type(text)
            except Exception as e2:  # noqa: BLE001
                print(f"[type] pynput fail: {e2}", flush=True)


_VK_NAMED = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "delete": 0x2E,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
}


def press_named_key(name: str) -> None:
    low = name.lower().strip()
    vk = _VK_NAMED.get(low)
    if vk is not None:
        try:
            _send_vk(vk)
            return
        except Exception:  # noqa: BLE001
            pass
    mapping = {
        "backspace": Key.backspace,
        "enter": Key.enter,
        "tab": Key.tab,
        "escape": Key.esc,
        "esc": Key.esc,
        "space": Key.space,
        "delete": Key.delete,
        "left": Key.left,
        "right": Key.right,
        "up": Key.up,
        "down": Key.down,
    }
    key = mapping.get(low)
    if key is None:
        return
    try:
        keyboard.press(key)
        keyboard.release(key)
    except Exception:  # noqa: BLE001
        pass


# keep move state below


def _boost_timer_resolution() -> None:
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:  # noqa: BLE001
        pass


def _boost_thread_priority() -> None:
    try:
        handle = ctypes.windll.kernel32.GetCurrentThread()
        ctypes.windll.kernel32.SetThreadPriority(handle, THREAD_PRIORITY_HIGHEST)
    except Exception:  # noqa: BLE001
        pass


def _send_input_xy(ix: int, iy: int) -> None:
    if not ix and not iy:
        return
    _input.mi.dx = ix
    _input.mi.dy = iy
    _input.mi.dwFlags = MOUSEEVENTF_MOVE
    _SendInput(1, ctypes.byref(_input), ctypes.sizeof(INPUT))


def _send_btn_flags(flags: int) -> None:
    """Button events via SendInput (same path as moves — more reliable than pynput)."""
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi.dx = 0
    inp.mi.dy = 0
    inp.mi.mouseData = 0
    inp.mi.dwFlags = flags
    inp.mi.time = 0
    inp.mi.dwExtraInfo = 0
    _SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def do_click(btn_name: str, count: int = 1) -> None:
    pair = _CLICK_FLAGS.get(btn_name)
    if not pair:
        return
    down, up = pair
    for _ in range(count):
        _send_btn_flags(down)
        _send_btn_flags(up)
    if btn_name == "left":
        schedule_editable_notify()


def do_press(btn_name: str) -> None:
    pair = _CLICK_FLAGS.get(btn_name)
    if pair:
        _send_btn_flags(pair[0])


def do_release(btn_name: str) -> None:
    pair = _CLICK_FLAGS.get(btn_name)
    if pair:
        _send_btn_flags(pair[1])


def _send_wheel(delta: int, *, horizontal: bool = False) -> None:
    if not delta:
        return
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi.dx = 0
    inp.mi.dy = 0
    # mouseData is unsigned DWORD; negative deltas need wrap
    inp.mi.mouseData = delta & 0xFFFFFFFF
    inp.mi.dwFlags = MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL
    inp.mi.time = 0
    inp.mi.dwExtraInfo = 0
    _SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def do_scroll(dx: float, dy: float) -> None:
    """Pixel-ish scroll deltas → Win32 wheel notches (more reliable than tiny pynput steps)."""
    global _scroll_acc_x, _scroll_acc_y
    with _scroll_lock:
        _scroll_acc_x += dx
        _scroll_acc_y += dy
        # ~28px finger travel ≈ one notch
        step = 28.0
        while _scroll_acc_y >= step:
            _scroll_acc_y -= step
            _send_wheel(WHEEL_DELTA)
        while _scroll_acc_y <= -step:
            _scroll_acc_y += step
            _send_wheel(-WHEEL_DELTA)
        while _scroll_acc_x >= step:
            _scroll_acc_x -= step
            _send_wheel(WHEEL_DELTA, horizontal=True)
        while _scroll_acc_x <= -step:
            _scroll_acc_x += step
            _send_wheel(-WHEEL_DELTA, horizontal=True)


def do_zoom(factor: float) -> None:
    """Ctrl + mouse wheel via the same Win32 path (pynput Ctrl + SendInput wheel often fails)."""
    steps = 1 if factor > 1 else -1 if factor < 1 else 0
    if steps == 0:
        return
    VK_CONTROL = 0x11
    KEYEVENTF_KEYUP = 0x0002
    print(f"[zoom] factor={factor} steps={steps}", flush=True)
    try:
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
        _send_wheel(WHEEL_DELTA * steps)
        ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
    except Exception:  # noqa: BLE001
        try:
            with keyboard.pressed(Key.ctrl):
                mouse.scroll(0, steps)
        except Exception:  # noqa: BLE001
            pass


def apply_move(dx: float, dy: float) -> None:
    """Immediate relative move + optional lead to hide Wi‑Fi RTT."""
    global _frac_x, _frac_y, _vx, _vy, _last_t
    if not dx and not dy:
        return

    now = time.perf_counter()
    with _move_lock:
        if _last_t > 0:
            dt_ms = (now - _last_t) * 1000.0
            if 1.0 < dt_ms < 40.0:
                inv = 1.0 / dt_ms
                # EMA of velocity in px/ms
                _vx = _vx * 0.45 + (dx * inv) * 0.55
                _vy = _vy * 0.45 + (dy * inv) * 0.55
                # Clamp so one huge frame can't overshoot
                if _vx > _PRED_V_MAX:
                    _vx = _PRED_V_MAX
                elif _vx < -_PRED_V_MAX:
                    _vx = -_PRED_V_MAX
                if _vy > _PRED_V_MAX:
                    _vy = _PRED_V_MAX
                elif _vy < -_PRED_V_MAX:
                    _vy = -_PRED_V_MAX
            elif dt_ms >= 40.0:
                # Gap / hitch — don't trust old velocity
                _vx = 0.0
                _vy = 0.0
        _last_t = now

        out_x = dx
        out_y = dy
        if PRED_MS > 0:
            out_x += _vx * PRED_MS
            out_y += _vy * PRED_MS

        _frac_x += out_x
        _frac_y += out_y
        ix = int(_frac_x)
        iy = int(_frac_y)
        if not ix and not iy:
            return
        _frac_x -= ix
        _frac_y -= iy
        _send_input_xy(ix, iy)


def decay_velocity() -> None:
    """Call on finger-up so prediction doesn't drift."""
    global _vx, _vy, _last_t
    with _move_lock:
        _vx = 0.0
        _vy = 0.0
        _last_t = 0.0


mouse = MouseController()
keyboard = KeyboardController()

# Presentation laser overlay (colored dot that follows the cursor)
_laser_state = {"on": False, "color": "#EF4444", "size": 44}
_laser_cmd_q: queue.SimpleQueue = queue.SimpleQueue()


def set_laser(
    on: bool, color: str | None = None, size: int | float | None = None
) -> None:
    if color:
        _laser_state["color"] = color
    if size is not None:
        try:
            s = int(size)
            _laser_state["size"] = max(16, min(120, s))
        except (TypeError, ValueError):
            pass
    _laser_state["on"] = bool(on)
    try:
        _laser_cmd_q.put_nowait(
            (
                "set",
                _laser_state["on"],
                _laser_state["color"],
                int(_laser_state["size"]),
            )
        )
    except Exception:  # noqa: BLE001
        pass


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    c = color.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) != 6:
        return 239, 68, 68
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except ValueError:
        return 239, 68, 68


def laser_overlay_worker() -> None:
    """
    Always-on-top click-through laser dot.
    Uses tkinter with root.update() (no mainloop) so it coexists with the GUI.
    """
    try:
        import tkinter as tk
    except Exception:  # noqa: BLE001
        print("[laser] tkinter unavailable — laser disabled", flush=True)
        return

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    user32 = ctypes.windll.user32
    size = int(_laser_state.get("size", 44) or 44)
    active = False
    color = str(_laser_state.get("color") or "#EF4444")

    root = tk.Tk()
    root.withdraw()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    try:
        root.attributes("-transparentcolor", "black")
    except Exception:  # noqa: BLE001
        pass
    root.configure(bg="black")
    root.geometry(f"{size}x{size}+0+0")

    canvas = tk.Canvas(
        root, width=size, height=size, bg="black", highlightthickness=0, bd=0
    )
    canvas.pack(fill="both", expand=True)
    glow = canvas.create_oval(2, 2, size - 2, size - 2, fill=color, outline="")
    inset = max(4, size // 3)
    core = canvas.create_oval(
        inset, inset, size - inset, size - inset, fill="#FFFFFF", outline=""
    )

    def make_clickthrough() -> None:
        try:
            root.update_idletasks()
            hwnd = int(root.winfo_id())
            parent = user32.GetParent(hwnd)
            if parent:
                hwnd = parent
            gwl_exstyle = -20
            style = user32.GetWindowLongW(hwnd, gwl_exstyle)
            user32.SetWindowLongW(
                hwnd,
                gwl_exstyle,
                style | 0x00080000 | 0x00000020 | 0x00000080,
            )
        except Exception as e:  # noqa: BLE001
            print(f"[laser] clickthrough warn: {e}", flush=True)

    def redraw(c: str, s: int) -> None:
        nonlocal glow, core, size
        size = max(16, min(120, int(s)))
        canvas.config(width=size, height=size)
        canvas.delete("all")
        glow = canvas.create_oval(2, 2, size - 2, size - 2, fill=c, outline="")
        inset = max(4, size // 3)
        core = canvas.create_oval(
            inset, inset, size - inset, size - inset, fill="#FFFFFF", outline=""
        )

    make_clickthrough()
    print("[laser] overlay ready (tk)", flush=True)

    try:
        while True:
            try:
                while True:
                    cmd = _laser_cmd_q.get_nowait()
                    if cmd[0] == "set":
                        active = bool(cmd[1])
                        new_color = str(cmd[2])
                        new_size = int(cmd[3]) if len(cmd) > 3 else size
                        if new_color != color or new_size != size:
                            color = new_color
                            redraw(color, new_size)
                        else:
                            color = new_color
                        print(
                            f"[laser] active={active} color={color} size={size}",
                            flush=True,
                        )
            except queue.Empty:
                pass

            if active:
                pt = POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                x = int(pt.x) - size // 2
                y = int(pt.y) - size // 2
                root.geometry(f"{size}x{size}+{x}+{y}")
                try:
                    root.deiconify()
                    root.attributes("-topmost", True)
                    root.lift()
                except Exception:  # noqa: BLE001
                    pass
            else:
                try:
                    root.withdraw()
                except Exception:  # noqa: BLE001
                    pass

            try:
                root.update()
            except tk.TclError:
                print("[laser] window closed", flush=True)
                break
            time.sleep(0.016)
    except Exception as e:  # noqa: BLE001
        print(f"[laser] overlay stopped: {e}", flush=True)
    finally:
        try:
            root.destroy()
        except Exception:  # noqa: BLE001
            pass


BUTTONS = {
    "left": Button.left,
    "right": Button.right,
    "middle": Button.middle,
}

MOD_KEYS = {
    "ctrl": Key.ctrl,
    "alt": Key.alt,
    "shift": Key.shift,
    "win": Key.cmd,
    "tab": Key.tab,
    "esc": Key.esc,
    "enter": Key.enter,
    "space": Key.space,
    "backspace": Key.backspace,
    "left": Key.left,
    "right": Key.right,
    "up": Key.up,
    "down": Key.down,
    "pageup": Key.page_up,
    "pagedown": Key.page_down,
    "f5": Key.f5,
    "b": "b",
    "volmute": Key.media_volume_mute,
    "volup": Key.media_volume_up,
    "voldown": Key.media_volume_down,
}

GESTURES = {
    # 3 fingers — Windows Precision defaults
    "three_finger_up": ["win", "tab"],
    "three_finger_down": ["win", "d"],
    "three_finger_left": ["alt", "shift", "tab"],
    "three_finger_right": ["alt", "tab"],
    "three_finger_tap": ["win", "s"],
    # 4 fingers — virtual desktops / Task View
    "four_finger_up": ["win", "tab"],
    "four_finger_down": ["win", "d"],
    "four_finger_left": ["win", "ctrl", "left"],
    "four_finger_right": ["win", "ctrl", "right"],
    "four_finger_tap": ["win", "a"],
}


def local_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return "127.0.0.1"


def _address_kind(iface: str) -> str:
    name = iface.lower()
    if "bluetooth" in name or name.startswith("bt"):
        return "bluetooth"
    if "wi-fi" in name or "wifi" in name or "wlan" in name or "inal" in name:
        return "wifi"
    if "ethernet" in name or name.startswith("eth") or "lan" in name:
        return "ethernet"
    return "other"


def local_ips() -> list[dict[str, str]]:
    """Every IPv4 address a phone could reach this host on, labelled by interface.

    local_ip() only ever answers with the default route's address — in practice
    Wi-Fi. A phone paired over Bluetooth PAN (tethering), or plugged into a second
    NIC, shares a different link, and that address would never be advertised. The
    preferred address comes first so callers that want a single answer can take
    the head of the list.

    Degrades to just local_ip() when psutil is unavailable, so no import failure
    can stop the host from starting.
    """
    preferred = local_ip()
    try:
        import psutil  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return [{"label": "Red", "ip": preferred, "kind": "other"}]

    try:
        stats = psutil.net_if_stats()
        found: list[dict[str, str]] = []
        for iface, addrs in psutil.net_if_addrs().items():
            link = stats.get(iface)
            if link is not None and not link.isup:
                continue
            for addr in addrs:
                if addr.family != socket.AF_INET:
                    continue
                ip = addr.address
                # Loopback is not reachable from the phone; 169.254.x.x means the
                # interface never got an address (APIPA), so it is not usable either.
                if not ip or ip.startswith("127.") or ip.startswith("169.254."):
                    continue
                found.append({"label": iface, "ip": ip, "kind": _address_kind(iface)})
    except Exception:  # noqa: BLE001
        return [{"label": "Red", "ip": preferred, "kind": "other"}]

    if not found:
        return [{"label": "Red", "ip": preferred, "kind": "other"}]

    # Default route first, then Bluetooth (the link the user just paired is the
    # one they are most likely looking for), then whatever is left.
    order = {"bluetooth": 1}
    found.sort(key=lambda a: (a["ip"] != preferred, order.get(a["kind"], 2)))
    return found


def ensure_firewall_rules(
    tcp_port: int = PORT, udp_port: int = UDP_PORT
) -> None:
    """Allow inbound LAN connections on Windows (idempotent)."""
    if sys.platform != "win32":
        return

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    def rule_exists(name: str) -> bool:
        try:
            chk = subprocess.run(
                [
                    "netsh",
                    "advfirewall",
                    "firewall",
                    "show",
                    "rule",
                    f"name={name}",
                ],
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=flags,
            )
        except Exception:  # noqa: BLE001
            return False
        out = (chk.stdout or "") + (chk.stderr or "")
        return chk.returncode == 0 and "No rules match" not in out

    for proto, port in (("TCP", tcp_port), ("UDP", udp_port)):
        name = f"ClicX Host {proto} {port}"
        if rule_exists(name):
            continue
        try:
            subprocess.run(
                [
                    "netsh",
                    "advfirewall",
                    "firewall",
                    "add",
                    "rule",
                    f"name={name}",
                    "dir=in",
                    "action=allow",
                    f"protocol={proto}",
                    f"localport={port}",
                    "profile=any",
                ],
                capture_output=True,
                timeout=8,
                creationflags=flags,
                check=False,
            )
            print(f"[firewall] added rule: {name}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[firewall] could not add {name}: {e}", flush=True)


def enable_tcp_nodelay_sock(sock: socket.socket | None) -> None:
    if sock is None:
        return
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        # Shrink / flush latency-oriented buffers when possible
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_QUICKACK, 1)  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            pass
    except OSError:
        pass


def enable_tcp_nodelay_ws(websocket: Any) -> None:
    sock = None
    try:
        sock = websocket.socket
    except Exception:  # noqa: BLE001
        sock = None
    if sock is None:
        transport = getattr(websocket, "transport", None)
        if transport is not None:
            try:
                sock = transport.get_extra_info("socket")
            except Exception:  # noqa: BLE001
                sock = None
    enable_tcp_nodelay_sock(sock)


def _endpoint_volume() -> Any | None:
    """Windows Core Audio master volume (speakers / default render)."""
    try:
        from pycaw.pycaw import AudioUtilities

        dev = AudioUtilities.GetSpeakers()
        return getattr(dev, "EndpointVolume", None)
    except Exception as e:  # noqa: BLE001
        print(f"[volume] endpoint unavailable: {e}", flush=True)
        return None


def get_volume_state() -> tuple[float, bool]:
    """Return (level 0..1, muted)."""
    ep = _endpoint_volume()
    if ep is None:
        return 0.5, False
    try:
        level = float(ep.GetMasterVolumeLevelScalar())
        muted = bool(ep.GetMute())
        return max(0.0, min(1.0, level)), muted
    except Exception:  # noqa: BLE001
        return 0.5, False


def set_volume_level(level: float) -> None:
    """Set master volume absolute (0..1). Unmutes when raising above 0."""
    ep = _endpoint_volume()
    if ep is None:
        # Fallback: relative media keys
        cur, _muted = 0.5, False
        target = max(0.0, min(1.0, float(level)))
        steps = int(round(abs(target - cur) * 50))
        key = "volup" if target >= cur else "voldown"
        for _ in range(max(1, min(25, steps))):
            press_hotkey([key])
        return
    try:
        target = max(0.0, min(1.0, float(level)))
        if target > 0 and ep.GetMute():
            ep.SetMute(0, None)
        ep.SetMasterVolumeLevelScalar(target, None)
        print(f"[volume] set {int(round(target * 100))}%", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[volume] set failed: {e}", flush=True)


def set_volume_mute(muted: bool) -> None:
    ep = _endpoint_volume()
    if ep is None:
        press_hotkey(["volmute"])
        return
    try:
        ep.SetMute(1 if muted else 0, None)
        print(f"[volume] mute={bool(muted)}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[volume] mute failed: {e}", flush=True)


def toggle_volume_mute() -> None:
    ep = _endpoint_volume()
    if ep is None:
        press_hotkey(["volmute"])
        return
    try:
        cur = bool(ep.GetMute())
        ep.SetMute(0 if cur else 1, None)
        print(f"[volume] mute toggled -> {not cur}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[volume] toggle failed: {e}", flush=True)


def bump_volume(delta: float) -> None:
    """Adjust master volume by delta (−1..1)."""
    ep = _endpoint_volume()
    if ep is None:
        press_hotkey(["volup" if delta > 0 else "voldown"])
        return
    try:
        cur = float(ep.GetMasterVolumeLevelScalar())
        set_volume_level(cur + float(delta))
    except Exception as e:  # noqa: BLE001
        print(f"[volume] bump failed: {e}", flush=True)


def handle_volume_message(data: dict[str, Any]) -> None:
    """
    {"t":"volume","action":"set","level":70}
    {"t":"volume","action":"mute"|"unmute"|"toggle"}
    {"t":"volume","action":"up"|"down"}
    level may be 0..100 or 0..1.
    """
    action = str(data.get("action", "set")).lower()
    if action in ("mute", "unmute", "toggle"):
        if action == "mute":
            set_volume_mute(True)
        elif action == "unmute":
            set_volume_mute(False)
        else:
            toggle_volume_mute()
        return
    if action in ("up", "down"):
        bump_volume(0.04 if action == "up" else -0.04)
        return
    # set absolute
    raw = data.get("level", data.get("value", 50))
    try:
        level = float(raw)
    except (TypeError, ValueError):
        return
    if level > 1.0:
        level = level / 100.0
    set_volume_level(level)


def press_hotkey(keys: list[str]) -> None:
    """Press a chord via Win32 keybd_event (more reliable than pynput for Win+Tab)."""
    vk_map = {
        "win": 0x5B,  # VK_LWIN
        "tab": 0x09,
        "alt": 0x12,  # VK_MENU
        "shift": 0x10,
        "ctrl": 0x11,
        "esc": 0x1B,
        "d": 0x44,
        "s": 0x53,
        "a": 0x41,
        "enter": 0x0D,
        "space": 0x20,
        "left": 0x25,  # VK_LEFT — slides / seek back
        "right": 0x27,  # VK_RIGHT — slides / seek forward
        "up": 0x26,
        "down": 0x28,
        "pageup": 0x21,
        "pagedown": 0x22,
        # Function keys F1-F12 (VK_F1..VK_F12) — keyboard screen / hotkeys
        "f1": 0x70,
        "f2": 0x71,
        "f3": 0x72,
        "f4": 0x73,
        "f5": 0x74,
        "f6": 0x75,
        "f7": 0x76,
        "f8": 0x77,
        "f9": 0x78,
        "f10": 0x79,
        "f11": 0x7A,
        "f12": 0x7B,
        # System volume (works without pynput media-key quirks)
        "volmute": 0xAD,  # VK_VOLUME_MUTE
        "voldown": 0xAE,  # VK_VOLUME_DOWN
        "volup": 0xAF,  # VK_VOLUME_UP
    }
    vks: list[int] = []
    for name in keys:
        low = name.lower()
        if low in vk_map:
            vks.append(vk_map[low])
        elif len(name) == 1:
            vks.append(ctypes.windll.user32.VkKeyScanW(ord(name.lower())) & 0xFF)
        else:
            # Fallback to pynput for exotic keys
            try:
                key = MOD_KEYS.get(low)
                if key is None:
                    return
                keyboard.press(key)
                keyboard.release(key)
            except Exception:  # noqa: BLE001
                pass
            return
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_EXTENDEDKEY = 0x0001
    # Volume / arrows are extended keys on many boards
    extended = {0xAD, 0xAE, 0xAF, 0x25, 0x26, 0x27, 0x28, 0x21, 0x22}
    try:
        for vk in vks:
            flags = KEYEVENTF_EXTENDEDKEY if vk in extended else 0
            ctypes.windll.user32.keybd_event(vk, 0, flags, 0)
        for vk in reversed(vks):
            flags = KEYEVENTF_KEYUP | (
                KEYEVENTF_EXTENDEDKEY if vk in extended else 0
            )
            ctypes.windll.user32.keybd_event(vk, 0, flags, 0)
        print(f"[hotkey] {keys} → {[hex(v) for v in vks]}", flush=True)
    except Exception:  # noqa: BLE001
        # Last resort: pynput
        try:
            resolved = []
            for name in keys:
                key = MOD_KEYS.get(name.lower())
                if key is None and len(name) == 1:
                    key = name.lower()
                if key is None:
                    return
                resolved.append(key)
            for key in resolved:
                keyboard.press(key)
            for key in reversed(resolved):
                keyboard.release(key)
        except Exception:  # noqa: BLE001
            pass


def handle_message(data: dict[str, Any], websocket: Any = None) -> dict | None:
    """Dispatch a control message.

    Returns a reply ``dict`` for reply-capable ``t`` types (status/action/media/
    app_volume/windows) or ``None`` for the fire-and-forget input types. The reply is
    sent back over ``websocket`` (when provided) by the frame handler.
    """
    t = data.get("t")

    if t == "move":
        apply_move(float(data.get("dx", 0)), float(data.get("dy", 0)))
        return None

    if t == "stop":
        decay_velocity()
        return

    if t == "click":
        decay_velocity()
        name = str(data.get("btn", "left"))
        count = int(data.get("n", 1))
        if count < 1:
            count = 1
        if count > 3:
            count = 3
        print(f"[click] {name} x{count}", flush=True)
        do_click(name, count)
        return

    if t == "down":
        do_press(str(data.get("btn", "left")))
        return

    if t == "up":
        decay_velocity()
        do_release(str(data.get("btn", "left")))
        return

    if t == "scroll":
        do_scroll(float(data.get("dx", 0)), float(data.get("dy", 0)))
        return

    if t == "zoom":
        do_zoom(float(data.get("factor", 1.0)))
        return

    if t == "gesture":
        name = str(data.get("name", ""))
        keys = GESTURES.get(name)
        if keys:
            print(f"[gesture] {name} → {keys}", flush=True)
            press_hotkey(keys)
        return

    if t == "hotkey":
        keys = data.get("keys")
        if isinstance(keys, list) and keys:
            # Route volume media keys through Core Audio (keys alone often fail)
            low = [str(k).lower() for k in keys]
            if low == ["volmute"]:
                toggle_volume_mute()
            elif low == ["volup"]:
                bump_volume(0.04)
            elif low == ["voldown"]:
                bump_volume(-0.04)
            else:
                press_hotkey([str(k) for k in keys])
        return

    if t == "volume":
        handle_volume_message(data)
        return

    if t == "laser":
        color = data.get("color")
        size = data.get("size")
        set_laser(
            bool(data.get("on", False)),
            str(color) if color else None,
            size,
        )
        print(
            f"[laser] on={bool(data.get('on'))} color={_laser_state['color']} "
            f"size={_laser_state['size']}",
            flush=True,
        )
        return

    if t == "type":
        text = data.get("text")
        if isinstance(text, str) and text:
            type_text(text)
        return

    if t == "key":
        name = data.get("name") or data.get("key")
        if isinstance(name, str) and name:
            press_named_key(name)
        return

    if t == "deck":
        bid = data.get("id")
        if bid:
            from deck_store import execute_button

            execute_button(str(bid))
        return None

    # --- Fase 1: centro de control (nuevos dominios, reply-capable) ---
    if t == "status":
        from system_status import collect_status
        from protocol import PROTOCOL_VERSION

        return collect_status(version=VERSION, ip=local_ip_print()) | {
            "t": "status",
            "protocol": PROTOCOL_VERSION,
        }

    if t == "action":
        from actions import handle_action

        return handle_action(data)

    if t == "usage":
        from usage_stats import handle_usage

        return handle_usage(data)

    if t == "media":
        from media import handle_media

        return handle_media(data)

    if t == "app_volume":
        from app_volume import handle_app_volume

        return handle_app_volume(data)

    if t == "windows":
        from window_manager import handle_windows

        return handle_windows(data)

    # --- Fase 2: integración (clipboard + file transfer) ---
    if t == "clipboard":
        from clipboard_sync import handle_clipboard

        return handle_clipboard(data, websocket)

    if t == "file":
        # file_transfer sends its own JSON + binary replies over `websocket`.
        from file_transfer import handle_file

        handle_file(data, websocket)
        return None

    raise ValueError(f"unknown message type: {t!r}")


def parse_compact_move(raw: str) -> tuple[float, float] | None:
    if len(raw) < 5 or raw[0] != "m" or raw[1] != ",":
        return None
    try:
        comma = raw.index(",", 2)
        return float(raw[2:comma]), float(raw[comma + 1 :])
    except (ValueError, IndexError):
        return None


def parse_compact_click(raw: str) -> tuple[str, int] | None:
    """c,left,1  or  c,right"""
    if len(raw) < 3 or raw[0] != "c" or raw[1] != ",":
        return None
    parts = raw.split(",")
    if len(parts) < 2:
        return None
    btn = parts[1].strip().lower() or "left"
    count = 1
    if len(parts) >= 3:
        try:
            count = int(parts[2])
        except ValueError:
            count = 1
    if count < 1:
        count = 1
    if count > 3:
        count = 3
    if btn not in _CLICK_FLAGS:
        return None
    return btn, count


def handle_raw_frame(raw: Any, websocket: Any = None) -> None:
    if isinstance(raw, (bytes, bytearray, memoryview)):
        buf = raw if isinstance(raw, (bytes, bytearray)) else bytes(raw)
        # If a file transfer session is armed, this frame is file data (any length).
        from file_transfer import consume_receive_frame

        reply = consume_receive_frame(websocket, buf)
        if reply is not None:
            if websocket is not None:
                try:
                    websocket.send(json.dumps(reply))
                except Exception:  # noqa: BLE001
                    pass
            return
        # Otherwise: the classic 8-byte move stream (unchanged).
        if len(buf) == 8:
            dx, dy = struct.unpack("<ff", buf)
            apply_move(dx, dy)
        return

    if not isinstance(raw, str):
        return

    if raw.startswith("m,"):
        parsed = parse_compact_move(raw)
        if parsed is not None:
            apply_move(parsed[0], parsed[1])
        return

    if raw.startswith("c,"):
        parsed = parse_compact_click(raw)
        if parsed is not None:
            btn, count = parsed
            decay_velocity()
            print(f"[click] {btn} x{count} (compact)", flush=True)
            do_click(btn, count)
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return
    if isinstance(data, dict):
        try:
            reply = handle_message(data, websocket)
        except Exception:  # noqa: BLE001
            return
        if isinstance(reply, dict) and websocket is not None:
            try:
                websocket.send(json.dumps(reply))
            except Exception:  # noqa: BLE001
                pass


def ws_handler(websocket: Any) -> None:
    _boost_thread_priority()
    enable_tcp_nodelay_ws(websocket)
    register_client(websocket)
    peer = None
    try:
        peer = websocket.remote_address
    except Exception:  # noqa: BLE001
        pass
    print(f"[+] ws {peer} (sync, NODELAY, pred={PRED_MS}ms)", flush=True)
    try:
        websocket.send(
            json.dumps(
                {
                    "t": "hello",
                    "name": "ClicX",
                    "version": VERSION,
                    "deck": __import__("deck_store").deck_for_client(),
                    **__import__("protocol").hello_payload(),
                }
            )
        )
    except Exception:  # noqa: BLE001
        unregister_client(websocket)
        return

    try:
        for raw in websocket:
            handle_raw_frame(raw, websocket)
    except Exception:  # noqa: BLE001
        pass
    finally:
        unregister_client(websocket)
        try:
            from file_transfer import cleanup_connection as ft_cleanup

            ft_cleanup(websocket)
        except Exception:  # noqa: BLE001
            pass
        try:
            from clipboard_sync import cleanup_connection as cb_cleanup

            cb_cleanup(websocket)
        except Exception:  # noqa: BLE001
            pass
        decay_velocity()
        print(f"[-] ws {peer}", flush=True)


def udp_loop() -> None:
    """Unreliable datagrams for moves — lowest latency path when the client supports UDP."""
    _boost_thread_priority()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
    sock.bind(("0.0.0.0", UDP_PORT))
    print(f"[*] UDP move port {UDP_PORT} ready", flush=True)
    while True:
        try:
            data, _addr = sock.recvfrom(64)
        except OSError:
            break
        if len(data) == 8:
            dx, dy = struct.unpack("<ff", data)
            apply_move(dx, dy)


def local_ip_print() -> str:
    return local_ip()


def is_admin() -> bool:
    """True when running elevated — required to control Task Manager / other admin UIs."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def relaunch_as_admin() -> bool:
    """
    Ask Windows to restart this process elevated (UAC).
    Returns True if the elevation request was accepted (caller should exit).
    """
    if is_admin():
        return False
    try:
        if getattr(sys, "frozen", False):
            exe = sys.executable
            params = " ".join(f'"{a}"' for a in sys.argv[1:])
        else:
            exe = sys.executable
            script = os.path.abspath(sys.argv[0])
            rest = " ".join(f'"{a}"' for a in sys.argv[1:])
            params = f'"{script}" {rest}'.strip()
        # SW_SHOWNORMAL = 1; return value > 32 means success
        rc = int(
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", exe, params, None, 1
            )
        )
        return rc > 32
    except Exception:  # noqa: BLE001
        return False


def ensure_elevated(*, interactive: bool = True) -> bool:
    """
    Prefer running as admin so SendInput works on elevated windows (Task Manager, etc.).
    If not elevated, try UAC relaunch. Returns True if this process is (now) admin.
    """
    if is_admin():
        return True
    if "--no-admin" in sys.argv:
        return False
    if interactive and relaunch_as_admin():
        # New elevated instance is starting — exit this one
        sys.exit(0)
    return False


def main_console() -> None:
    _boost_timer_resolution()
    _boost_thread_priority()

    ip = local_ip_print()
    ensure_firewall_rules()
    print("=" * 52, flush=True)
    print("  ClicX Host (ultra-low latency)", flush=True)
    print("=" * 52, flush=True)
    print(f"  IP:          {ip}", flush=True)
    print(f"  WebSocket:   ws://{ip}:{PORT}", flush=True)
    print(f"  UDP moves:   {ip}:{UDP_PORT} (8-byte float32 dx,dy)", flush=True)
    print(f"  Prediction:  {PRED_MS} ms (CLICX_PRED_MS)", flush=True)
    print("  Path:        sync WS + SendInput (no asyncio queue)", flush=True)
    print("=" * 52, flush=True)

    threading.Thread(target=udp_loop, name="clicx-udp", daemon=True).start()
    threading.Thread(
        target=laser_overlay_worker, name="clicx-laser", daemon=True
    ).start()

    # compression=None / sync serve: no asyncio scheduling between frames
    with sync_serve(
        ws_handler,
        "0.0.0.0",
        PORT,
        compression=None,
        max_size=2**16,
        # Ping less often — less noise on the wire while moving
        ping_interval=60,
        ping_timeout=60,
    ) as server:
        server.serve_forever()


def main() -> None:
    """Default: interactive GUI. Use --console for terminal-only mode."""
    # Without elevation, Windows blocks input into Task Manager and other admin apps.
    ensure_elevated(interactive=True)

    if "--console" in sys.argv:
        if not is_admin():
            print(
                "AVISO: sin privilegios de administrador no podés controlar "
                "el Administrador de tareas ni otras ventanas elevadas.",
                flush=True,
            )
        main_console()
        return
    from gui_app import run_gui

    run_gui()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBye.")
        sys.exit(0)
