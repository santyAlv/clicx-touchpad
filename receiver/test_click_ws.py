"""Sanity: send a left-click JSON frame to the local ClicX host."""

from __future__ import annotations

import json
import sys

from websockets.sync.client import connect

PORT = 51234


def main() -> int:
    url = f"ws://127.0.0.1:{PORT}"
    try:
        with connect(url, open_timeout=3, close_timeout=2) as ws:
            hello = ws.recv(timeout=3)
            print("hello:", hello)
            ws.send(json.dumps({"t": "click", "btn": "left", "n": 1}))
            print("sent: click left")
    except Exception as exc:  # noqa: BLE001
        print("FAIL:", exc)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
