"""Stream Deck layout + .bat scripts for shell actions."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
import webbrowser
from pathlib import Path
from typing import Any, Literal

DeckActionKind = Literal["hotkey", "volume", "shell", "url"]

CONFIG_NAME = "deck.json"
SCRIPTS_DIR_NAME = "scripts"


def config_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    path = base / "ClicX"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return config_dir() / CONFIG_NAME


def scripts_dir() -> Path:
    path = config_dir() / SCRIPTS_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _new_id() -> str:
    return uuid.uuid4().hex[:10]


def default_config() -> dict[str, Any]:
    def hk(
        label: str, icon: str, color: str, keys: list[str], hint: str = ""
    ) -> dict[str, Any]:
        btn: dict[str, Any] = {
            "id": _new_id(),
            "label": label,
            "icon": icon,
            "color": color,
            "action": {"kind": "hotkey", "keys": keys},
        }
        if hint:
            btn["hint"] = hint
        return btn

    def vol(label: str, icon: str, color: str, action: str) -> dict[str, Any]:
        return {
            "id": _new_id(),
            "label": label,
            "icon": icon,
            "color": color,
            "action": {"kind": "volume", "action": action},
        }

    def sh(label: str, icon: str, color: str, command: str, cwd: str = "", app: str = "") -> dict[str, Any]:
        action: dict[str, Any] = {
            "kind": "shell",
            "command": command,
            "cwd": cwd,
        }
        if app:
            action["app"] = app
        return {
            "id": _new_id(),
            "label": label,
            "icon": icon,
            "color": color,
            "action": action,
        }

    return {
        "version": 1,
        "pages": [
            {
                "id": "page1",
                "title": "Atajos",
                "buttons": [
                    hk("Copiar", "copy-outline", "#9CB080", ["ctrl", "c"]),
                    hk("Pegar", "clipboard-outline", "#618764", ["ctrl", "v"]),
                    hk("Deshacer", "arrow-undo-outline", "#9CB080", ["ctrl", "z"]),
                    hk("Guardar", "save-outline", "#618764", ["ctrl", "s"]),
                    hk("Escritorio", "desktop-outline", "#2B5748", ["win", "d"]),
                    hk("Tareas", "layers-outline", "#618764", ["win", "tab"]),
                    hk("Buscar", "search-outline", "#9CB080", ["win", "s"]),
                    hk("Captura", "camera-outline", "#618764", ["win", "shift", "s"], "⇧⌘S"),
                    hk("Esc", "close-circle-outline", "#2B5748", ["esc"]),
                    hk("Enter", "return-down-back-outline", "#9CB080", ["enter"]),
                    hk("Espacio", "remove-outline", "#618764", ["space"]),
                    sh("npm i", "terminal-outline", "#9CB080", "npm i"),
                ],
            },
            {
                "id": "page2",
                "title": "Media",
                "buttons": [
                    hk("Anterior", "play-skip-back", "#618764", ["left"]),
                    hk("Play", "play", "#9CB080", ["space"]),
                    hk("Siguiente", "play-skip-forward", "#9CB080", ["right"]),
                    vol("Vol +", "volume-high-outline", "#9CB080", "up"),
                    vol("Mute", "volume-mute-outline", "#2B5748", "mute"),
                    vol("Vol −", "volume-low-outline", "#618764", "down"),
                    hk("Apps", "apps-outline", "#618764", ["alt", "tab"]),
                    hk("Cerrar", "close-outline", "#2B5748", ["alt", "f4"], "⌥F4"),
                    hk("Izquierda", "chevron-back-outline", "#9CB080", ["win", "left"]),
                    hk("Derecha", "chevron-forward-outline", "#9CB080", ["win", "right"]),
                    hk("Arriba", "chevron-up-outline", "#618764", ["pageup"]),
                    hk("Abajo", "chevron-down-outline", "#618764", ["pagedown"]),
                ],
            },
        ],
    }


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.is_file():
        cfg = default_config()
        save_config(cfg)
        return cfg
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "pages" not in data:
            raise ValueError("invalid deck")
        return data
    except Exception:  # noqa: BLE001
        cfg = default_config()
        save_config(cfg)
        return cfg


def save_config(cfg: dict[str, Any]) -> None:
    from icon_extract import attach_icons

    attach_icons(cfg)
    path = config_path()
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    regenerate_scripts(cfg)
    broadcast_deck()


def broadcast_deck() -> None:
    try:
        import main as core

        core.broadcast_json({"t": "deckSync", "deck": deck_for_client()})
    except Exception:  # noqa: BLE001
        pass


def find_button(cfg: dict[str, Any], button_id: str) -> dict[str, Any] | None:
    for page in cfg.get("pages", []):
        if not isinstance(page, dict):
            continue
        for btn in page.get("buttons", []):
            if isinstance(btn, dict) and str(btn.get("id")) == button_id:
                return btn
    return None


def script_path(button_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in button_id)
    return scripts_dir() / f"{safe}.bat"


def _bat_content(command: str, cwd: str) -> str:
    lines = ["@echo off", "setlocal"]
    cwd = cwd.strip()
    if cwd:
        lines.append(f'cd /d "{cwd}"')
    for line in command.replace("\r\n", "\n").split("\n"):
        line = line.strip()
        if line:
            lines.append(line)
    lines.append("endlocal")
    return "\r\n".join(lines) + "\r\n"


def regenerate_scripts(cfg: dict[str, Any]) -> None:
    scripts_dir().mkdir(parents=True, exist_ok=True)
    active: set[str] = set()
    for page in cfg.get("pages", []):
        if not isinstance(page, dict):
            continue
        for btn in page.get("buttons", []):
            if not isinstance(btn, dict):
                continue
            action = btn.get("action")
            if not isinstance(action, dict):
                continue
            kind = action.get("kind")
            if kind not in ("shell", "app"):
                continue
            bid = str(btn.get("id", ""))
            if not bid:
                continue
            if kind == "app":
                app = str(action.get("app", "")).strip()
                cmd = f'start "" "{app}"' if app else ""
                cwd = ""
            else:
                cmd = str(action.get("command", "")).strip()
                cwd = str(action.get("cwd", ""))
            if not cmd:
                continue
            path = script_path(bid)
            path.write_text(
                _bat_content(cmd, cwd),
                encoding="utf-8",
            )
            active.add(path.name)

    for old in scripts_dir().glob("*.bat"):
        if old.name not in active:
            try:
                old.unlink()
            except OSError:
                pass


def execute_button(button_id: str) -> None:
    import main as core

    cfg = load_config()
    btn = find_button(cfg, button_id)
    if not btn:
        print(f"[deck] unknown button {button_id}", flush=True)
        return
    action = btn.get("action")
    if not isinstance(action, dict):
        return
    kind = action.get("kind")
    label = btn.get("label", button_id)

    if kind == "hotkey":
        keys = action.get("keys")
        if isinstance(keys, list) and keys:
            print(f"[deck] {label} hotkey {keys}", flush=True)
            core.press_hotkey([str(k) for k in keys])
        return

    if kind == "volume":
        vol_action = str(action.get("action", "mute")).lower()
        print(f"[deck] {label} volume {vol_action}", flush=True)
        if vol_action == "up":
            core.bump_volume(0.04)
        elif vol_action == "down":
            core.bump_volume(-0.04)
        else:
            core.toggle_volume_mute()
        return

    if kind == "url":
        url = str(action.get("url", "")).strip()
        if url:
            print(f"[deck] {label} open {url}", flush=True)
            webbrowser.open(url)
        return

    if kind in ("shell", "app"):
        path = script_path(button_id)
        if not path.is_file():
            regenerate_scripts(cfg)
        if not path.is_file():
            print(f"[deck] missing script for {button_id}", flush=True)
            return
        print(f"[deck] {label} run {path.name}", flush=True)
        flags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        try:
            subprocess.Popen(
                ["cmd.exe", "/c", str(path)],
                cwd=str(scripts_dir()),
                creationflags=flags,
            )
        except OSError as e:
            print(f"[deck] run failed: {e}", flush=True)
        return

    print(f"[deck] unsupported action {kind!r}", flush=True)


DEFAULT_ACCENT = "#9CB080"


def get_accent() -> str:
    return str(load_config().get("accent", DEFAULT_ACCENT))


def set_accent(color: str) -> None:
    """Persist the app accent and push it to connected phones."""
    cfg = load_config()
    cfg["accent"] = color
    save_config(cfg)


def deck_for_client() -> dict[str, Any]:
    from icon_extract import attach_icons

    cfg = load_config()
    attach_icons(cfg)
    pages = []
    for page in cfg.get("pages", []):
        if not isinstance(page, dict):
            continue
        buttons = []
        for btn in page.get("buttons", []):
            if not isinstance(btn, dict):
                continue
            entry = {
                "id": str(btn.get("id", "")),
                "label": str(btn.get("label", "Btn")),
                "icon": str(btn.get("icon", "ellipse-outline")),
                "color": str(btn.get("color", "#9CB080")),
                "action": btn.get("action"),
            }
            if btn.get("hint"):
                entry["hint"] = str(btn["hint"])
            if btn.get("iconB64"):
                entry["iconB64"] = str(btn["iconB64"])
            buttons.append(entry)
        pages.append(
            {
                "id": str(page.get("id", _new_id())),
                "title": str(page.get("title", "Página")),
                "buttons": buttons,
            }
        )
    return {
        "version": cfg.get("version", 1),
        "accent": str(cfg.get("accent", DEFAULT_ACCENT)),
        "pages": pages,
    }
