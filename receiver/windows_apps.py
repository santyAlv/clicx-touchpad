"""Windows app inventory — Dokke-style adapter for ClicX."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from icon_extract import resolve_app_path

# Dokke: PINNED_PAGE_SIZE = 8, PINNED_MAX_PAGES = 5
DECK_PAGE_SIZE = 8
DECK_MAX_PAGES = 5

_CACHE: list[dict[str, str]] | None = None
_LOADING = False


def _start_menu_dirs() -> list[Path]:
    dirs: list[Path] = []
    program_data = os.environ.get("ProgramData", "")
    app_data = os.environ.get("APPDATA", "")
    if program_data:
        dirs.append(
            Path(program_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        )
    if app_data:
        dirs.append(Path(app_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return [d for d in dirs if d.is_dir()]


def _resolve_lnk_batch(lnk_paths: list[str]) -> dict[str, str]:
    """Resolve many .lnk targets in one PowerShell call."""
    if not lnk_paths or sys.platform != "win32":
        return {}
    targets: dict[str, str] = {}
    chunk_size = 80
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    for i in range(0, len(lnk_paths), chunk_size):
        chunk = lnk_paths[i : i + chunk_size]
        lines = []
        for p in chunk:
            esc = p.replace("'", "''")
            lines.append(f"$s = $sh.CreateShortcut('{esc}'); '{esc}|' + $s.TargetPath")
        script = (
            "$sh = New-Object -ComObject WScript.Shell; "
            + "; ".join(lines)
        )
        try:
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", script],
                text=True,
                timeout=30,
                creationflags=flags,
            )
            for line in out.splitlines():
                if "|" not in line:
                    continue
                lnk, target = line.split("|", 1)
                target = target.strip()
                if target:
                    targets[lnk.strip()] = target
        except Exception:  # noqa: BLE001
            continue
    return targets


def list_installed_apps(*, refresh: bool = False) -> list[dict[str, str]]:
    """Return sorted unique apps from Start Menu shortcuts."""
    global _CACHE, _LOADING
    if _CACHE is not None and not refresh:
        return _CACHE
    if _LOADING and _CACHE is not None:
        return _CACHE

    _LOADING = True
    found: dict[str, dict[str, str]] = {}
    lnks: list[Path] = []
    for root in _start_menu_dirs():
        try:
            lnks.extend(root.rglob("*.lnk"))
        except OSError:
            continue

    targets = _resolve_lnk_batch([str(p) for p in lnks])
    for lnk in lnks:
        name = lnk.stem.strip()
        if not name:
            continue
        key = name.lower()
        if key in found:
            continue
        raw = targets.get(str(lnk), "")
        path = resolve_app_path(raw) if raw else resolve_app_path(str(lnk))
        if not path:
            continue
        if Path(path).suffix.lower() not in {".exe", ".bat", ".cmd"}:
            continue
        found[key] = {"name": name, "path": path}

    _CACHE = sorted(found.values(), key=lambda a: a["name"].lower())
    _LOADING = False
    return _CACHE


def search_apps(query: str) -> list[dict[str, str]]:
    q = query.strip().lower()
    apps = list_installed_apps()
    if not q:
        return apps
    return [a for a in apps if q in a["name"].lower()]
