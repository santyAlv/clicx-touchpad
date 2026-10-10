"""ClicX file transfer (Fase 2).

Implements ``{"t":"file","action":...}`` using JSON control messages + raw binary
frames over the same WebSocket (never Base64). Two fixed destination/source
folders only:

  * ``<root>/From Phone``  — files the phone uploads  (safe write target on PC)
  * ``<root>/From PC``     — files the PC offers for the phone to download

Everything is validated and bounded on the host side (§2.10, §4.1):

  * name: basename only, length capped, no separators / traversal / absolute /
    drive / reserved names
  * size: ``0 <= size <= MAX_FILE_SIZE``
  * extension: uploads to the PC reject a small blocklist of launchable types
  * path: the host joins ``name`` to a fixed root and re-checks containment
  * chunks: size capped (WS ``max_size=65536``), offsets must match the stream
    position, out-of-order data aborts the transfer
  * cancel / timeout: partial files are removed, sessions swept by a daemon thread
  * connection drop: ``cleanup_connection`` closes handles and removes partials

Protocol (C=client/phone, H=host/PC):

  Upload (phone → PC):
    C→H meta {id,name,size}            H→C meta_ack {id,offset:0} (WB of staging file)
    C→H chunk {id,offset,size} + BIN   H→C chunk_ack {id,received}
    C→H done {id}                      H→C done_ack {id}
    C→H cancel {id}                    H→C cancel_ack {id}
  Download (PC → phone):
    C→H list {folder}                  H→C list {folder,files[]}
    C→H download {id,name}             H→C meta {id,name,size}
    C→H pull {id,size}                 H→C chunk {id,offset,size} + BIN
                                       H→C done {id}  (when the source is exhausted)

The receiver correlates a raw binary frame with the session armed by the *last*
``chunk`` JSON (see ``consume_receive_frame``); the 8-byte move stream is never
touched (binary frames are only consumed when a session is armed).
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

#: Max length of a transferred file name (basename).
MAX_FILENAME_LEN = 150
#: Upper bound for any single file transfer (bytes). Configurable constant.
MAX_FILE_SIZE = 200 * 1024 * 1024  # 200 MiB
#: Upper bound for one binary chunk. Must fit the WS server max_size (65536).
MAX_CHUNK_BYTES = 64 * 1024  # 64 KiB
#: Transfer "no progress" timeout before a session is cleaned up (seconds).
TRANSFER_TIMEOUT_S = 240.0
#: Session id shape (short, safe, provided by the client).
SID_RE = re.compile(r"^[A-Za-z0-9_-]{1,24}$")
#: Sanity bound on concurrent transfer sessions per connection.
MAX_SESSIONS = 8

#: Extensions never written to the PC (uploads). Launchable/script types that an
#: accidental double-click could execute. Applies phone→PC only.
UPLOAD_BLOCKED_EXT = frozenset(
    {
        ".bat",
        ".cmd",
        ".com",
        ".cpl",
        ".dll",
        ".exe",
        ".jar",
        ".jse",
        ".lnk",
        ".msi",
        ".msp",
        ".ps1",
        ".psd1",
        ".psm1",
        ".scr",
        ".sys",
        ".vbe",
        ".vbs",
        ".wsh",
    }
)

#: Windows reserved device names (must never be used as a file name).
_RESERVED_NAMES = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{i}" for i in range(1, 10)),
        *(f"lpt{i}" for i in range(1, 10)),
    }
)

_DIRS = ("from_phone", "from_pc")


def _default_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home()) / "ClicX"


def transfer_root() -> Path:
    """Base directory for transfers (default %LOCALAPPDATA%/ClicX)."""
    override = os.environ.get("CLICX_TRANSFER_ROOT")
    if override:
        return Path(override)
    return _default_root()


def transfer_dir(folder: str) -> Path:
    d = f"from_{folder}" if folder in ("phone", "pc") else folder
    if d not in _DIRS:
        raise ValueError(f"bad folder: {folder!r}")
    root = transfer_root()
    return root / ("From Phone" if d == "from_phone" else "From PC")


# TEMP DIAG: metadata-only logging of the upload path (never file/clipboard content).
_DIAG_LOG = Path(os.environ.get("CLICX_DIAG_LOG", str(_default_root() / "file_transfer_diag.log")))
_diag_lock = threading.Lock()


def _diag_log(event: str, payload: dict[str, Any]) -> None:
    try:
        with _diag_lock:
            _DIAG_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(_DIAG_LOG, "a", encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {event} {json.dumps(payload, ensure_ascii=False)}\n")
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Validation (pure, unit-testable)
# ---------------------------------------------------------------------------

def valid_sid(sid: Any) -> bool:
    return isinstance(sid, str) and bool(SID_RE.match(sid))


def validate_name(name: Any) -> str | None:
    """Return an error string if ``name`` is not safe, else None."""
    if not isinstance(name, str) or not name.strip():
        return "bad name"
    name = name.strip()
    if len(name) > MAX_FILENAME_LEN:
        return "name too long"
    if name in (".", "..") or ".." in name.split("/") or ".." in name.split("\\"):
        return "path traversal"
    if "/" in name or "\\" in name:
        return "path traversal"
    if os.path.isabs(name):
        return "absolute path"
    if ":" in name or "\x00" in name:
        return "bad name"
    stem = name.split(".")[0].lower()
    if stem in _RESERVED_NAMES:
        return "reserved name"
    return None


def validate_size(size: Any) -> str | None:
    if not isinstance(size, (int, float)) or isinstance(size, bool):
        return "bad size"
    size = int(size)
    if size < 0:
        return "negative size"
    if size > MAX_FILE_SIZE:
        return "size too large"
    return None


def _ext_of(name: str) -> str:
    try:
        return Path(name).suffix.lower()
    except Exception:  # noqa: BLE001
        return ""


def validate_upload_name(name: Any) -> str | None:
    """Name checks for phone→PC uploads (adds extension blocklist)."""
    err = validate_name(name)
    if err:
        return err
    ext = _ext_of(name)
    if ext in UPLOAD_BLOCKED_EXT:
        return "blocked extension"
    return None


def _normalize_upload_name(name: Any) -> Any:
    """Strip a benign Android storage-claim prefix before validation.

    Android exposes a file's name through content URIs as ``<volume>:<name>``
    (e.g. ``primary:prueba.txt`` for a file at the sdcard root). A literal
    ``:`` is not a valid Windows filename character, so the host rejects it as
    "bad name". This strips ONLY a leading ``<identifier>:`` claim and then the
    full, unchanged security validation runs on the cleaned basename. It is NOT
    a relaxation: traversal / absolute / separators / reserved / blocked
    extensions still apply to the resulting basename.
    """
    if not isinstance(name, str):
        return name
    stripped = name.strip()
    m = re.match(r"^[A-Za-z0-9_-]+:(?![/\\])", stripped)
    if m:
        return stripped[m.end():]
    return stripped


def _safe_final_path(folder: str, name: str) -> Path | None:
    """Join ``name`` under the rooted transfer folder; verify containment."""
    root = transfer_dir(folder).resolve()
    candidate = (root / name).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


# ---------------------------------------------------------------------------
# Session state (per connection)
# ---------------------------------------------------------------------------

class _Session:
    __slots__ = (
        "sid",
        "direction",  # "recv" (phone→PC) | "send" (PC→phone)
        "name",
        "total",
        "received",
        "fh",
        "final_path",
        "staging_path",
        "last_activity",
        "awaiting_size",
        "armed",
        "finalized",
    )

    def __init__(self, sid: str, direction: str, name: str, total: int) -> None:
        self.sid = sid
        self.direction = direction
        self.name = name
        self.total = total
        self.received = 0
        self.fh = None
        self.final_path = None
        self.staging_path = None
        self.last_activity = time.time()
        self.awaiting_size = 0
        self.armed = False
        self.finalized = False


_lock = threading.Lock()
_sessions: dict[Any, dict[str, _Session]] = {}
_armed: dict[Any, str | None] = {}


def _conn_key(conn: Any) -> Any:
    return id(conn)


def _get_sessions(conn: Any) -> dict[str, _Session]:
    with _lock:
        return _sessions.setdefault(_conn_key(conn), {})


def _send_json(websocket: Any, payload: dict[str, Any]) -> None:
    if websocket is None:
        return
    import json

    try:
        websocket.send(json.dumps(payload))
    except Exception:  # noqa: BLE001
        pass


def _send_bytes(websocket: Any, data: bytes) -> None:
    if websocket is None:
        return
    try:
        websocket.send(data)
    except Exception:  # noqa: BLE001
        pass


def _remove_file(path: Any) -> None:
    try:
        if path is not None:
            Path(path).unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass


def _close_session(sess: _Session, *, keep_final: bool) -> None:
    try:
        if sess.fh is not None:
            sess.fh.close()
            sess.fh = None
    except Exception:  # noqa: BLE001
        pass
    if not keep_final:
        _remove_file(sess.staging_path)


def _finalize_recv(sess: _Session) -> bool:
    """Move the staging file into its final place once fully received."""
    if sess.fh is not None:
        try:
            sess.fh.close()
            sess.fh = None
        except Exception:  # noqa: BLE001
            pass
    try:
        if sess.staging_path and Path(sess.staging_path).exists():
            target = Path(sess.final_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                _remove_file(target)
            Path(sess.staging_path).replace(target)
            sess.finalized = True
            return True
        if sess.finalized or (sess.final_path and Path(sess.final_path).exists()):
            sess.finalized = True
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def _drop_session(conn: Any, sid: str) -> None:
    key = _conn_key(conn)
    with _lock:
        sess = _sessions.get(key, {}).get(sid)
        _sessions.get(key, {}).pop(sid, None)
        if _armed.get(key) == sid:
            _armed[key] = None
        if not _sessions.get(key):
            _sessions.pop(key, None)
    if sess is not None:
        _close_session(sess, keep_final=sess.finalized)


def _err(action: str, sid: Any, reason: str) -> dict:
    return {"t": "file", "action": action, "ok": False, "error": reason, "id": sid}


def _touch(sess: _Session) -> None:
    sess.last_activity = time.time()


# ---------------------------------------------------------------------------
# Timeout sweeper (daemon thread, lazy start)
# ---------------------------------------------------------------------------

_sweep_started = False
_sweep_lock = threading.Lock()


def _sweeper() -> None:
    while True:
        try:
            _sweep_expired()
        except Exception:  # noqa: BLE001
            pass
        time.sleep(30)


def _sweep_expired() -> None:
    now = time.time()
    with _lock:
        snapshot = [
            (conn, sid, sess)
            for conn, group in list(_sessions.items())
            for sid, sess in list(group.items())
            if now - sess.last_activity > TRANSFER_TIMEOUT_S
        ]
    for conn, sid, _sess in snapshot:
        _drop_session(conn, sid)


def _ensure_sweeper() -> None:
    global _sweep_started
    with _sweep_lock:
        if _sweep_started:
            return
        _sweep_started = True
        threading.Thread(target=_sweeper, name="clicx-transfer-sweep", daemon=True).start()


# ---------------------------------------------------------------------------
# Binary frame consumption (called from handle_raw_frame for any binary frame)
# ---------------------------------------------------------------------------

def consume_receive_frame(conn: Any, buf: bytes) -> dict | None:
    """Consume a raw binary frame for the armed transfer session.

    Returns a reply dict to send to the client (``chunk_ack`` or error), or None
    if no session was armed (the caller then treats the frame as a move stream).
    """
    key = _conn_key(conn)
    with _lock:
        sid = _armed.get(key)
        sess = _sessions.get(key, {}).get(sid) if sid else None
        if sess is None or not sess.armed:
            return None
        if len(buf) != sess.awaiting_size:
            sess_armed = sess
            _armed[key] = None
        else:
            sess_armed = None
    if sess_armed is not None:
        sid = sess_armed.sid
        _drop_session(conn, sid)
        return _err("chunk", sid, "size mismatch")
    try:
        sess.fh.write(buf)
        sess.received += len(buf)
        sess.armed = False
        sess.awaiting_size = 0
        _touch(sess)
        received = sess.received
        done = received >= sess.total
    except Exception as e:  # noqa: BLE001
        sid = sess.sid
        _drop_session(conn, sid)
        return _err("chunk", sid, f"write failed: {e}")

    if done:
        ok = _finalize_recv(sess)
        if not ok:
            _drop_session(conn, sid)
            return _err("chunk", sid, "finalize failed")
        # Session stays registered (finalized) until the client sends `done`.
    return {"t": "file", "action": "chunk_ack", "ok": True, "id": sid, "received": received}


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

def handle_file(data: dict[str, Any], websocket: Any = None) -> None:
    """Handle a ``t:"file"`` control message. Sends replies (JSON + binary)."""
    _ensure_sweeper()
    action = str(data.get("action", "")).lower()

    if action == "list":
        folder = str(data.get("folder", ""))
        if folder not in _DIRS:
            _send_json(websocket, _err(action, None, "bad folder"))
            return
        files = _list_folder(folder)
        _send_json(
            websocket,
            {"t": "file", "action": "list", "folder": folder, "files": files},
        )
        return

    if action == "meta":
        handle_upload_meta(data, websocket)
        return

    if action == "chunk":
        handle_upload_chunk(data, websocket)
        return

    if action == "done":
        handle_upload_done(data, websocket)
        return

    if action == "cancel":
        sid = str(data.get("id", ""))
        if valid_sid(sid):
            _drop_session(websocket, sid)
        _send_json(websocket, {"t": "file", "action": "cancel_ack", "ok": True, "id": sid})
        return

    if action == "download":
        handle_download_request(data, websocket)
        return

    if action == "pull":
        handle_pull(data, websocket)
        return

    _send_json(websocket, _err(action, data.get("id"), "unknown"))


def _list_folder(folder: str) -> list[dict[str, Any]]:
    root = transfer_dir(folder)
    out: list[dict[str, Any]] = []
    try:
        if not root.exists():
            return out
        for entry in sorted(os.listdir(root)):
            p = root / entry
            if p.is_file() and not entry.startswith("."):
                out.append({"name": entry, "size": p.stat().st_size})
    except Exception:  # noqa: BLE001
        pass
    return out


def handle_upload_meta(data: dict[str, Any], websocket: Any = None) -> None:
    sid = data.get("id")
    if not valid_sid(sid):
        _send_json(websocket, _err("meta", sid, "bad id"))
        return
    # TEMP DIAG (metadata only, no file/clipboard content)
    _diag_log("upload_meta_in",
              {"id": sid, "action": data.get("action"),
               "name": data.get("name"), "name_type": type(data.get("name")).__name__,
               "size": data.get("size"), "all_keys": sorted(data.keys())})
    name = _normalize_upload_name(data.get("name"))
    _diag_log("upload_meta_normalized", {"id": sid, "name": name,
                                         "name_type": type(name).__name__})
    name_err = validate_upload_name(name)
    if name_err:
        _send_json(websocket, _err("meta", sid, name_err))
        return
    size_err = validate_size(data.get("size"))
    if size_err:
        _send_json(websocket, _err("meta", sid, size_err))
        return
    name = str(name or "").strip()
    size = int(data.get("size"))
    final = _safe_final_path("from_phone", name)
    if final is None:
        _send_json(websocket, _err("meta", sid, "bad destination"))
        return

    sessions = _get_sessions(websocket)
    with _lock:
        if len(sessions) >= MAX_SESSIONS and sid not in sessions:
            _send_json(websocket, _err("meta", sid, "too many sessions"))
            return
        if sid in sessions:
            _send_json(websocket, _err("meta", sid, "id in use"))
            return
        root = transfer_dir("from_phone")
        root.mkdir(parents=True, exist_ok=True)
        staging = root / f".{name}.part-{sid}"
        fh = None
        try:
            fh = open(staging, "wb")  # noqa: SIM115
        except Exception as e:  # noqa: BLE001
            _send_json(websocket, _err("meta", sid, f"open failed: {e}"))
            return
        sess = _Session(sid, "recv", name, size)
        sess.fh = fh
        sess.final_path = final
        sess.staging_path = staging
        sessions[sid] = sess

    _send_json(
        websocket,
        {"t": "file", "action": "meta_ack", "ok": True, "id": sid, "offset": 0},
    )


def handle_upload_chunk(data: dict[str, Any], websocket: Any = None) -> None:
    sid = str(data.get("id", ""))
    sess = _get_sessions(websocket).get(sid)
    if sess is None or sess.direction != "recv":
        _send_json(websocket, _err("chunk", sid, "no session"))
        return
    if sess.armed:
        _send_json(websocket, _err("chunk", sid, "frame pending"))
        return
    offset = data.get("offset")
    size = data.get("size")
    try:
        offset = int(offset)
        size = int(size)
    except (TypeError, ValueError):
        _drop_session(websocket, sid)
        _send_json(websocket, _err("chunk", sid, "bad offset/size"))
        return
    if offset != sess.received:
        _drop_session(websocket, sid)
        _send_json(websocket, _err("chunk", sid, "offset mismatch"))
        return
    if size < 1 or size > MAX_CHUNK_BYTES:
        _drop_session(websocket, sid)
        _send_json(websocket, _err("chunk", sid, "bad size"))
        return
    if offset + size > sess.total:
        _drop_session(websocket, sid)
        _send_json(websocket, _err("chunk", sid, "exceeds total"))
        return
    sess.awaiting_size = size
    sess.armed = True
    _touch(sess)
    with _lock:
        _armed[_conn_key(websocket)] = sid
    # The next binary frame is consumed by consume_receive_frame (no JSON reply
    # here so the client knows the file bytes follow this control message).


def handle_upload_done(data: dict[str, Any], websocket: Any = None) -> None:
    sid = str(data.get("id", ""))
    sess = _get_sessions(websocket).get(sid)
    if sess is None or sess.direction != "recv":
        _send_json(websocket, _err("done", sid, "no session"))
        return
    if sess.armed:
        _drop_session(websocket, sid)
        _send_json(websocket, _err("done", sid, "frame pending"))
        return
    if sess.received != sess.total:
        _drop_session(websocket, sid)
        _send_json(
            websocket,
            _err("done", sid, f"incomplete {sess.received}/{sess.total}"),
        )
        return
    ok = sess.total == 0 or _finalize_recv(sess)
    if not ok:
        _drop_session(websocket, sid)
        _send_json(websocket, _err("done", sid, "finalize failed"))
        return
    if sess.total == 0 and not _finalize_recv(sess):
        # Empty upload: create the empty final file explicitly.
        try:
            Path(sess.final_path).parent.mkdir(parents=True, exist_ok=True)
            Path(sess.final_path).touch()
            sess.finalized = True
        except Exception:  # noqa: BLE001
            pass
    _drop_session(websocket, sid)
    _send_json(websocket, {"t": "file", "action": "done_ack", "ok": True, "id": sid})


def handle_download_request(data: dict[str, Any], websocket: Any = None) -> None:
    sid = data.get("id")
    if not valid_sid(sid):
        _send_json(websocket, _err("download", sid, "bad id"))
        return
    name_err = validate_name(data.get("name"))
    if name_err:
        _send_json(websocket, _err("download", sid, name_err))
        return
    name = str(data.get("name")).strip()
    source = _safe_final_path("from_pc", name)
    if source is None or not source.is_file():
        _send_json(websocket, _err("download", sid, "not found"))
        return
    size = source.stat().st_size
    size_err = validate_size(size)
    if size_err:
        _send_json(websocket, _err("download", sid, size_err))
        return
    sessions = _get_sessions(websocket)
    with _lock:
        if len(sessions) >= MAX_SESSIONS and sid not in sessions:
            _send_json(websocket, _err("download", sid, "too many sessions"))
            return
        if sid in sessions:
            _send_json(websocket, _err("download", sid, "id in use"))
            return
        try:
            fh = open(source, "rb")  # noqa: SIM115
        except Exception as e:  # noqa: BLE001
            _send_json(websocket, _err("download", sid, f"open failed: {e}"))
            return
        sess = _Session(sid, "send", name, size)
        sess.fh = fh
        sess.final_path = source
        sessions[sid] = sess

    _send_json(
        websocket,
        {"t": "file", "action": "meta", "ok": True, "id": sid, "name": name, "size": size},
    )


def handle_pull(data: dict[str, Any], websocket: Any = None) -> None:
    sid = str(data.get("id", ""))
    sess = _get_sessions(websocket).get(sid)
    if sess is None or sess.direction != "send":
        _send_json(websocket, _err("pull", sid, "no session"))
        return
    try:
        want = int(data.get("size"))
    except (TypeError, ValueError):
        _drop_session(websocket, sid)
        _send_json(websocket, _err("pull", sid, "bad size"))
        return
    if want < 1 or want > MAX_CHUNK_BYTES:
        _drop_session(websocket, sid)
        _send_json(websocket, _err("pull", sid, "bad size"))
        return

    remaining = sess.total - sess.received
    if remaining <= 0:
        _drop_session(websocket, sid)
        _send_json(websocket, {"t": "file", "action": "done", "ok": True, "id": sid})
        return

    take = min(want, remaining)
    offset = sess.received
    try:
        data_b = sess.fh.read(take)
    except Exception as e:  # noqa: BLE001
        _drop_session(websocket, sid)
        _send_json(websocket, _err("pull", sid, f"read failed: {e}"))
        return
    if not data_b:
        _drop_session(websocket, sid)
        _send_json(websocket, _err("pull", sid, "read failed"))
        return
    sess.received += len(data_b)
    _touch(sess)
    _send_json(
        websocket,
        {
            "t": "file",
            "action": "chunk",
            "ok": True,
            "id": sid,
            "offset": offset,
            "size": len(data_b),
        },
    )
    _send_bytes(websocket, data_b)


def cleanup_connection(conn: Any) -> None:
    """Clean up transfer state when a client disconnects. Never raises."""
    try:
        key = _conn_key(conn)
        with _lock:
            group = _sessions.pop(key, {})
            _armed.pop(key, None)
        for sid, sess in group.items():
            _close_session(sess, keep_final=False)
    except Exception:  # noqa: BLE001
        pass