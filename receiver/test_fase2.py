"""Standalone tests for Fase 2 host modules (clipboard_sync, file_transfer).

Run:  python receiver/test_fase2.py   (with receiver deps installed in the venv)

SAFETY: clipboard Win32 IO is monkeypatched to no-ops (no real clipboard side
effects). File transfers are confined to an isolated temp root via
CLICX_TRANSFER_ROOT. No external processes, no network I/O.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

_F = tempfile.mkdtemp(prefix="clicx_test_fase2_")
os.environ["CLICX_TRANSFER_ROOT"] = _F  # isolate all transfer folders before import

from file_transfer import (  # noqa: E402
    MAX_CHUNK_BYTES,
    MAX_FILE_SIZE,
    transfer_dir,
    transfer_root,
    validate_name,
    validate_size,
    validate_upload_name,
    valid_sid,
)
from clipboard_sync import _HISTORY_MAX  # noqa: E402
import file_transfer as ft  # noqa: E402
import clipboard_sync as cb  # noqa: E402

_FAILURES = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _FAILURES
    if not cond:
        _FAILURES += 1
        print(f"FAIL {name}  {detail}")
    else:
        print(f"ok   {name}")


def reset_handlers():
    """Reset clipboard state and replace all Win32 IO with fake seams."""
    cb._clear_history()
    cb._sync_on.clear()
    cb._last_text.clear()
    cb._fake_text = {"v": ""}

    def fake_get() -> str:
        return cb._fake_text["v"]

    def fake_set(text: str) -> bool:
        cb._fake_text["v"] = text
        return True

    cb._get_clipboard_text = fake_get
    cb._set_clipboard_text = fake_set


class FakeWS:
    """Collects JSON str + binary bytes sent by the host, keyed by conn."""

    def __init__(self):
        self.sent: list[bytes] = []

    def send(self, data):
        if isinstance(data, str):
            self.sent.append(("json", data))
        else:
            self.sent.append(("bin", bytes(data)))

    # ---- helpers for tests ----
    def json_msgs(self):
        return [json.loads(d) for kind, d in self.sent if kind == "json"]

    def last_json(self):
        msgs = self.json_msgs()
        return msgs[-1] if msgs else None

    def binary(self):
        return [d for kind, d in self.sent if kind == "bin"]


# ---------------------------------------------------------------------------
# clipboard_sync
# ---------------------------------------------------------------------------

def test_clipboard_set_history_clear():
    reset_handlers()
    ws = FakeWS()

    # set → ok and records history; fake set writes to fake clipboard
    r = cb.handle_clipboard({"t": "clipboard", "action": "set", "text": "aaa"}, ws)
    check("set ok", r["ok"] is True)
    h = cb.handle_clipboard({"t": "clipboard", "action": "history"}, ws)
    check("history has 1 item", len(h["items"]) == 1 and h["items"][0]["text"] == "aaa")

    # chars recorded as length only, never content in logs (assert len matches)
    check("history stores len", h["items"][0]["len"] == len("aaa"))

    # bad text
    r = cb.handle_clipboard({"t": "clipboard", "action": "set"}, ws)
    check("set missing text denied", r["ok"] is False)

    for i in range(_HISTORY_MAX + 5):
        cb.handle_clipboard({"t": "clipboard", "action": "set", "text": f"entry{i}"}, ws)
    h = cb.handle_clipboard({"t": "clipboard", "action": "history"}, ws)
    check("history bounded FIFO", len(h["items"]) <= _HISTORY_MAX)
    check("oldest evicted", all(i["text"] != "aaa" for i in h["items"]))

    r = cb.handle_clipboard({"t": "clipboard", "action": "clear"}, ws)
    check("clear ok", r["ok"] is True)
    h = cb.handle_clipboard({"t": "clipboard", "action": "history"}, ws)
    check("history empty after clear", h["items"] == [])


def test_clipboard_no_content_logged():
    # We can't observe logs directly, but we can ensure the reply dicts for
    # set/history/clear never contain the raw clipboard text in unexpected
    # fields and that "set" echoes text at all (it should NOT).
    reset_handlers()
    ws = FakeWS()
    r = cb.handle_clipboard({"t": "clipboard", "action": "set", "text": "SECRET-996"}, ws)
    # The set reply carries no 'text' (content lives only on the clipboard).
    check("set reply does not echo content", "text" not in r)
    check("set reply hides content", str(r).find("SECRET-996") == -1)


def test_clipboard_push_back_and_unknown():
    reset_handlers()
    ws = FakeWS()
    cb._fake_text["v"] = "from-pc"
    r = cb.handle_clipboard({"t": "clipboard", "action": "push_back"}, ws)
    check("push_back returns PC text", r["action"] == "push" and r["text"] == "from-pc")

    r = cb.handle_clipboard({"t": "clipboard", "action": "bogus"}, ws)
    check("unknown action denied", r["ok"] is False)


def test_clipboard_sync_default_off_and_toggle():
    reset_handlers()
    ws = FakeWS()
    # Default: not registered in _sync_on.
    check("sync off by default", cb._sync_on.get(ws) is None)
    r = cb.handle_clipboard({"t": "clipboard", "action": "sync", "on": True}, ws)
    check("sync on ok", r["ok"] is True and r["on"] is True)
    check("sync on registered", cb._sync_on.get(ws) is True)
    # Disabling removes from sync set.
    r = cb.handle_clipboard({"t": "clipboard", "action": "sync", "on": False}, ws)
    check("sync off ok", r["ok"] is True and r["on"] is False)
    check("sync off deregistered", cb._sync_on.get(ws) is False)

    # cleanup_connection clears per-conn state
    cb.handle_clipboard({"t": "clipboard", "action": "sync", "on": True}, ws)
    cb.cleanup_connection(ws)
    check("cleanup removes sync state", cb._sync_on.get(ws) is None)


# ---------------------------------------------------------------------------
# file_transfer: validation (pure)
# ---------------------------------------------------------------------------

def test_name_validation():
    check("valid name ok", validate_name("foto.jpg") is None)
    check("empty string", validate_name("   ") is not None)
    check("too long", validate_name("x" * (150 + 1)) is not None)
    check("traversal ../", validate_name("../etc/passwd") is not None)
    check("traversal ..\\", validate_name("..\\etc") is not None)
    check("absolute /", validate_name("/etc/passwd") is not None)
    check("absolute Windows drive", validate_name("C:\\foo") is not None)
    check("traversal hidden ..", validate_name("..") is not None)
    check("colon", validate_name("a:b") is not None)
    check("nul byte", validate_name("a\x00b") is not None)
    check("reserved con", validate_name("con.txt") is not None)
    check("reserved com1", validate_name("com1") is not None)
    check("normal ok", validate_name("report final.pdf") is None)
    # Extension blocklist applies to uploads only.
    check("upload blocked exe", validate_upload_name("virus.exe") is not None)
    check("upload blocked ps1", validate_upload_name("x.ps1") is not None)
    check("upload ok txt", validate_upload_name("note.txt") is None)
    # download allows exe (source is a PC file being offered).
    check("download allows exe", validate_name("app.exe") is None)


def test_size_validation():
    check("size 0 ok", validate_size(0) is None)
    check("size 1024 ok", validate_size(1024) is None)
    check("size negative", validate_size(-1) is not None)
    check("size above max", validate_size(MAX_FILE_SIZE + 1) is not None)
    check("size non-numeric", validate_size("many") is not None)
    check("bool treated invalid", validate_size(True) is not None)


def test_sid_validation():
    check("valid sid", valid_sid("ab-1_xZ") is True)
    check("empty sid", valid_sid("") is False)
    check("space sid", valid_sid("a b") is False)
    check("too long sid", valid_sid("x" * 25) is False)
    check("non-str sid", valid_sid(123) is False)


# ---------------------------------------------------------------------------
# file_transfer: full upload (phone -> PC) end-to-end
# ---------------------------------------------------------------------------

def test_upload_roundtrip():
    reset_handlers()
    ws = FakeWS()
    root = transfer_dir("from_phone")
    sid = "up1"
    name = "hola.txt"
    payload = b"hello clicx upload!" * 1000  # > one chunk, <= max

    ft.handle_file({"t": "file", "action": "meta", "id": sid, "name": name, "size": len(payload)}, ws)
    ack = ws.last_json()
    check("meta_ack ok", ack["action"] == "meta_ack" and ack["ok"])
    staging = root / f".{name}.part-{sid}"
    check("staging opened", (root / f".{name}.part-{sid}").exists())

    # Send chunks in pieces using handle_upload_chunk + consume_receive_frame.
    pos = 0
    received_tot = 0
    while pos < len(payload):
        chunk = payload[pos:pos + MAX_CHUNK_BYTES]
        ft.handle_file({"t": "file", "action": "chunk", "id": sid, "offset": pos, "size": len(chunk)}, ws)
        reply = ft.consume_receive_frame(ws, chunk)
        check("consume returned ack", reply is not None and reply["ok"])
        received_tot = reply["received"]
        pos += len(chunk)

    check("received full", received_tot == len(payload))
    ft.handle_file({"t": "file", "action": "done", "id": sid}, ws)
    check("done_ack ok", ws.last_json()["action"] == "done_ack")
    final = root / name
    check("final file created", final.exists())
    check("final content matches", final.read_bytes() == payload)
    check("staging removed", not (root / f".{name}.part-{sid}").exists())


def test_upload_empty_file():
    reset_handlers()
    ws = FakeWS()
    root = transfer_dir("from_phone")
    sid = "up0"
    ft.handle_file({"t": "file", "action": "meta", "id": sid, "name": "empty.bin", "size": 0}, ws)
    check("meta_ack empty ok", ws.last_json()["ok"])
    ft.handle_file({"t": "file", "action": "done", "id": sid}, ws)
    check("done_ack empty ok", ws.last_json()["ok"])
    check("empty final created", (root / "empty.bin").exists())


def test_upload_path_traversal_rejected():
    reset_handlers()
    ws = FakeWS()
    for bad in ("../escape.txt", "..\\escape.txt", "/etc/passwd", "C:\\x.txt"):
        ft.handle_file({"t": "file", "action": "meta", "id": "x1", "name": bad, "size": 1}, ws)
        check(f"traversal '{bad}' rejected", ws.last_json()["ok"] is False)


def test_upload_blocked_extension():
    reset_handlers()
    ws = FakeWS()
    ft.handle_file({"t": "file", "action": "meta", "id": "x2", "name": "bad.exe", "size": 1}, ws)
    check("upload exe rejected", ws.last_json()["ok"] is False and "extension" in ws.last_json().get("error",""))


def test_upload_size_limits():
    reset_handlers()
    ws = FakeWS()
    ft.handle_file({"t": "file", "action": "meta", "id": "x3", "name": "big.bin", "size": MAX_FILE_SIZE + 1}, ws)
    check("oversize rejected", ws.last_json()["ok"] is False)


def test_upload_cancel_and_cleanup():
    reset_handlers()
    ws = FakeWS()
    root = transfer_dir("from_phone")
    sid = "cancel1"
    payload = b"partial-data"
    ft.handle_file({"t": "file", "action": "meta", "id": sid, "name": "tmp.txt", "size": 1000}, ws)
    staging = root / ".tmp.txt.part-cancel1"
    check("staging created", staging.exists())
    ft.handle_file({"t": "file", "action": "chunk", "id": sid, "offset": 0, "size": len(payload)}, ws)
    ft.consume_receive_frame(ws, payload)
    ft.handle_file({"t": "file", "action": "cancel", "id": sid}, ws)
    check("cancel_ack ok", ws.last_json()["ok"])
    check("partial staging removed on cancel", not staging.exists())
    check("no final file", not (root / "tmp.txt").exists())


def test_upload_cleanup_on_disconnect():
    reset_handlers()
    ws = FakeWS()
    root = transfer_dir("from_phone")
    sid = "disc1"
    ft.handle_file({"t": "file", "action": "meta", "id": sid, "name": "gone.txt", "size": 100}, ws)
    staging = root / ".gone.txt.part-disc1"
    check("staging created", staging.exists())
    ft.cleanup_connection(ws)
    check("partial removed on disconnect", not staging.exists())


def test_upload_offset_and_chunk_mismatch():
    reset_handlers()
    ws = FakeWS()
    ft.handle_file({"t": "file", "action": "meta", "id": "off1", "name": "o.bin", "size": 100}, ws)
    # wrong offset
    ft.handle_file({"t": "file", "action": "chunk", "id": "off1", "offset": 50, "size": 10}, ws)
    check("offset mismatch rejected", ws.last_json()["ok"] is False)
    # bad size 0
    ft.handle_file({"t": "file", "action": "meta", "id": "off2", "name": "o2.bin", "size": 100}, ws)
    ft.handle_file({"t": "file", "action": "chunk", "id": "off2", "offset": 0, "size": 0}, ws)
    check("zero chunk rejected", ws.last_json()["ok"] is False)
    # exceeds total
    ft.handle_file({"t": "file", "action": "meta", "id": "off3", "name": "o3.bin", "size": 10}, ws)
    ft.handle_file({"t": "file", "action": "chunk", "id": "off3", "offset": 0, "size": 11}, ws)
    check("chunk exceeds total rejected", ws.last_json()["ok"] is False)
    # binary with wrong size -> abort
    ft.handle_file({"t": "file", "action": "meta", "id": "off4", "name": "o4.bin", "size": 100}, ws)
    ft.handle_file({"t": "file", "action": "chunk", "id": "off4", "offset": 0, "size": 10}, ws)
    bad = ft.consume_receive_frame(ws, b"toolongbyteshere")
    check("size-mismatch frame aborts", bad is not None and bad["ok"] is False)


# ---------------------------------------------------------------------------
# Phone -> PC through the REAL host dispatcher (main.handle_raw_frame).
# Reproduces exactly how the mobile app's ClipboardScreen "Enviar a PC" (set)
# and FilesScreen upload (meta JSON + binary chunks + done) reach the host.
# ---------------------------------------------------------------------------

def test_phone_to_pc_clipboard_set_real_dispatch():
    reset_handlers()
    ws = FakeWS()
    # ClipboardScreen "Enviar a PC" sends {"t":"clipboard","action":"set","text":...}.
    import main
    main.handle_raw_frame(json.dumps({"t": "clipboard", "action": "set", "text": "phone-2-pc"}), ws)
    # The JSON reply is emitted by the dispatcher on the fake websocket.
    reply = ws.last_json()
    check("set reply via real dispatch", reply and reply.get("action") == "set" and reply.get("ok") is True)
    # And the fake clipboard seam now holds the phone text (no content logged).
    check("phone text reached host clipboard", cb._fake_text.get("v") == "phone-2-pc")
    h = cb.handle_clipboard({"t": "clipboard", "action": "history"}, ws)
    check("set recorded to history", any(i["text"] == "phone-2-pc" for i in h["items"]))


def test_phone_to_pc_upload_real_dispatch():
    reset_handlers()
    ws = FakeWS()
    import main
    root = transfer_dir("from_phone")
    sid = "p2p1"
    name = "from_phone_diag.txt"
    payload = b"phone->pc real dispatch bytes " * 5000
    # meta
    main.handle_raw_frame(json.dumps({"t": "file", "action": "meta", "id": sid, "name": name, "size": len(payload)}), ws)
    check("meta_ack via real dispatch", ws.last_json()["action"] == "meta_ack" and ws.last_json()["ok"])
    # chunks: JSON frame then binary frame (exactly like the app's send+sendBinary)
    pos = 0
    while pos < len(payload):
        chunk = payload[pos:pos + MAX_CHUNK_BYTES]
        main.handle_raw_frame(json.dumps({"t": "file", "action": "chunk", "id": sid, "offset": pos, "size": len(chunk)}), ws)
        main.handle_raw_frame(chunk, ws)
        pos += len(chunk)
    # done
    main.handle_raw_frame(json.dumps({"t": "file", "action": "done", "id": sid}), ws)
    check("done_ack via real dispatch", ws.last_json()["action"] == "done_ack" and ws.last_json()["ok"])
    final = root / name
    check("final file via real dispatch", final.exists())
    check("final content matches", final.read_bytes() == payload)


def test_phone_to_pc_prueba_txt_accept_and_null_name_reject():
    # The real FilesScreen sends {"t":"file","action":"meta","id","name","size"}.
    # A clean basename like "prueba.txt" MUST be accepted, while the broken
    # file.name -> null (undefined) case that caused "bad name" is rejected.
    reset_handlers()
    ws = FakeWS()
    import main

    # 1) Real case: a simple, valid file name is accepted end-to-end.
    sid1 = "pru1"
    payload = b"hola"
    main.handle_raw_frame(
        json.dumps({"t": "file", "action": "meta", "id": sid1, "name": "prueba.txt", "size": len(payload)}), ws
    )
    ack = ws.last_json()
    check("prueba.txt meta accepted", ack["action"] == "meta_ack" and ack["ok"] is True)
    main.handle_raw_frame(json.dumps({"t": "file", "action": "chunk", "id": sid1, "offset": 0, "size": len(payload)}), ws)
    main.handle_raw_frame(payload, ws)
    main.handle_raw_frame(json.dumps({"t": "file", "action": "done", "id": sid1}), ws)
    check("prueba.txt done", ws.last_json()["action"] == "done_ack" and ws.last_json()["ok"])
    check("prueba.txt on disk", (transfer_dir("from_phone") / "prueba.txt").read_bytes() == payload)

    # 2) The bug: file.name being null (undefined) -> host rejects "bad name".
    ft.handle_file({"t": "file", "action": "meta", "id": "pru2", "name": None, "size": 3}, ws)
    r = ws.last_json()
    check("null name -> bad name", r["ok"] is False and r["error"] == "bad name")

    # 3) Empty string name -> also "bad name".
    ft.handle_file({"t": "file", "action": "meta", "id": "pru3", "name": "", "size": 3}, ws)
    r = ws.last_json()
    check("empty name -> bad name", r["ok"] is False and r["error"] == "bad name")


def test_phone_to_pc_android_claim_prefix_normalized():
    # The installed FilesScreen derives the upload name from Android content-
    # URI basename, which for a file at the sdcard root is "<volume>:<name>",
    # e.g. "primary:prueba.txt". The host normalizes (strips) the benign
    # storage-claim prefix so the file lands as a clean basename, WITHOUT
    # relaxing any security check.
    reset_handlers()
    ws = FakeWS()
    import main

    # 1) The real broken value "primary:prueba.txt" is now accepted end-to-end
    #    and lands on disk as "prueba.txt".
    sid1 = "clm1"
    payload = b"hola"
    main.handle_raw_frame(
        json.dumps({"t": "file", "action": "meta", "id": sid1, "name": "primary:prueba.txt", "size": len(payload)}), ws
    )
    ack = ws.last_json()
    check("primary: claim meta accepted", ack["action"] == "meta_ack" and ack["ok"] is True)
    main.handle_raw_frame(json.dumps({"t": "file", "action": "chunk", "id": sid1, "offset": 0, "size": len(payload)}), ws)
    main.handle_raw_frame(payload, ws)
    main.handle_raw_frame(json.dumps({"t": "file", "action": "done", "id": sid1}), ws)
    check("primary: claim done", ws.last_json()["action"] == "done_ack" and ws.last_json()["ok"])
    check("primary: claim lands clean basename",
          (transfer_dir("from_phone") / "prueba.txt").read_bytes() == payload)

    # 2) Security is NOT relaxed: a colon-prefixed traversal is still rejected
    #    (stripping 'a:' yields '..\\etc' which fails the traversal check).
    sid2 = "clm2"
    main.handle_raw_frame(
        json.dumps({"t": "file", "action": "meta", "id": sid2, "name": "a:..\\..\\etc", "size": 3}), ws
    )
    r = ws.last_json()
    check("colon-prefixed traversal still rejected", r["ok"] is False and r["error"] == "path traversal")

    # 3) A leading <identifier>: claim is stripped and the remaining basename
    #    is validated normally, so "my:file.txt" lands as "file.txt".
    sid3 = "clm3"
    main.handle_raw_frame(
        json.dumps({"t": "file", "action": "meta", "id": sid3, "name": "my:file.txt", "size": 3}), ws
    )
    main.handle_raw_frame(json.dumps({"t": "file", "action": "chunk", "id": sid3, "offset": 0, "size": 3}), ws)
    main.handle_raw_frame(b"abc", ws)
    main.handle_raw_frame(json.dumps({"t": "file", "action": "done", "id": sid3}), ws)
    check("my: claim lands clean basename",
          ws.last_json()["action"] == "done_ack" and
          (transfer_dir("from_phone") / "file.txt").read_bytes() == b"abc")


# ---------------------------------------------------------------------------
# file_transfer: download (PC -> phone)
# ---------------------------------------------------------------------------

def _seed_from_pc(*files):
    d = ft.transfer_dir("from_pc")
    d.mkdir(parents=True, exist_ok=True)
    for name, content in files:
        (d / name).write_bytes(content)
    return d


def test_list_and_download():
    reset_handlers()
    _seed_from_pc(("share.txt", b"pc content here"))

    ws = FakeWS()
    ft.handle_file({"t": "file", "action": "list", "folder": "from_pc"}, ws)
    r = ws.last_json()
    check("list ok", r["action"] == "list" and isinstance(r["files"], list))
    files = {f["name"]: f["size"] for f in r["files"]}
    check("list contains seeded file", "share.txt" in files and files["share.txt"] == len(b"pc content here"))
    check("list sizes positive", files["share.txt"] > 0)

    # list bad folder
    ft.handle_file({"t": "file", "action": "list", "folder": "nope"}, ws)
    check("bad folder list", ws.last_json()["ok"] is False)

    # download + pull
    sid = "down1"
    ft.handle_file({"t": "file", "action": "download", "id": sid, "name": "share.txt"}, ws)
    meta = ws.last_json()
    check("download meta ok", meta["action"] == "meta" and meta["ok"] and meta["size"] == len(b"pc content here"))

    ft.handle_file({"t": "file", "action": "pull", "id": sid, "size": MAX_CHUNK_BYTES}, ws)
    chunk = ws.last_json()
    check("pull chunk meta", chunk["action"] == "chunk" and chunk["ok"])
    bin_frame = ws.binary()
    check("binary sent after pull", bin_frame and bin_frame[-1] == b"pc content here")
    check("pull offset 0 size", chunk["offset"] == 0 and chunk["size"] == len(b"pc content here"))

    # exhausted -> done
    ft.handle_file({"t": "file", "action": "pull", "id": sid, "size": 10}, ws)
    check("exhausted sends done", ws.last_json()["action"] == "done" and ws.last_json()["ok"])


def test_download_not_found_and_traversal():
    reset_handlers()
    ws = FakeWS()
    ft.handle_file({"t": "file", "action": "download", "id": "d1", "name": "missing.txt"}, ws)
    check("download missing denied", ws.last_json()["ok"] is False)
    ft.handle_file({"t": "file", "action": "download", "id": "d2", "name": "../x.txt"}, ws)
    check("download traversal denied", ws.last_json()["ok"] is False)


def test_binary_not_consumed_without_arm():
    reset_handlers()
    ws = FakeWS()
    # An 8-byte frame with no armed session -> None (treated as moves).
    r = ft.consume_receive_frame(ws, b"\x01\x02\x03\x04\x05\x06\x07\x08")
    check("no session -> None", r is None)


def main() -> int:
    test_clipboard_set_history_clear()
    test_clipboard_no_content_logged()
    test_clipboard_push_back_and_unknown()
    test_clipboard_sync_default_off_and_toggle()
    test_phone_to_pc_clipboard_set_real_dispatch()

    test_name_validation()
    test_size_validation()
    test_sid_validation()

    test_upload_roundtrip()
    test_upload_empty_file()
    test_upload_path_traversal_rejected()
    test_upload_blocked_extension()
    test_upload_size_limits()
    test_upload_cancel_and_cleanup()
    test_upload_cleanup_on_disconnect()
    test_upload_offset_and_chunk_mismatch()
    test_phone_to_pc_upload_real_dispatch()
    test_phone_to_pc_prueba_txt_accept_and_null_name_reject()
    test_phone_to_pc_android_claim_prefix_normalized()

    test_list_and_download()
    test_download_not_found_and_traversal()
    test_binary_not_consumed_without_arm()

    print("\n---")
    print(f"{_FAILURES} failure(s)")
    return 1 if _FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
