"""Standalone tests for the Claude / Codex usage collector.

Run:  python receiver/test_usage_stats.py

Builds its own transcripts under a temp directory and points CLAUDE_HOME /
CODEX_HOME at them, so it never reads the machine's real usage data.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

_FAILURES = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _FAILURES
    if cond:
        print(f"ok   {name}")
    else:
        _FAILURES += 1
        print(f"FAIL {name} {detail}")


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def claude_line(ts: float, out_tokens: int, model: str = "claude-opus-5") -> str:
    return json.dumps(
        {
            "timestamp": iso(ts),
            "message": {
                "model": model,
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": out_tokens,
                    "cache_read_input_tokens": 1000,
                    "cache_creation_input_tokens": 5,
                },
            },
        }
    ) + "\n"


def codex_line(ts: float, used_percent: float) -> str:
    return json.dumps(
        {
            "timestamp": iso(ts),
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": None,
                "rate_limits": {
                    "plan_type": "pro",
                    "primary": {
                        "used_percent": used_percent,
                        "window_minutes": 10080,
                        "resets_at": int(ts) + 3600,
                    },
                },
            },
        }
    ) + "\n"


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="clicx-usage-"))
    try:
        os.environ["CLAUDE_HOME"] = str(root / "claude")
        os.environ["CODEX_HOME"] = str(root / "codex")
        # Caps land in the temp dir too, never in the machine's real config.
        os.environ["CLICX_USAGE_LIMITS"] = str(root / "usage_limits.json")
        cdir = root / "claude" / "projects" / "D--demo"
        xdir = root / "codex" / "sessions" / "2026" / "01" / "01"
        cdir.mkdir(parents=True)
        xdir.mkdir(parents=True)
        transcript = cdir / "session.jsonl"

        import usage_stats as u

        u._files.clear()
        now = time.time()

        # An old window, then a fresh one: only the fresh one is "in progress".
        transcript.write_text(
            claude_line(now - 9 * 3600, 100)
            + claude_line(now - 8.5 * 3600, 100)
            + claude_line(now - 600, 300)
            + claude_line(now - 300, 200),
            encoding="utf-8",
        )
        (xdir / "rollout-a.jsonl").write_text(codex_line(now - 60, 42.5), encoding="utf-8")

        r = u.collect_usage()
        week = r["claude"]["week"]
        check("counts every message in the week", week["messages"] == 4, str(week["messages"]))
        # billable = (10 in + 5 cache write + out) per message, cache reads excluded.
        check("cache reads stay out of the headline", week["billable"] == 4 * 15 + 700, str(week["billable"]))
        check("cache reads are still reported", week["tokens"]["cacheRead"] == 4000, str(week["tokens"]))

        session = r["claude"]["session"]
        check("the open window is the recent one", session is not None and session["messages"] == 2, str(session))
        check(
            "window resets five hours after it opened",
            session is not None
            and abs(session["resetsAt"] - session["startedAt"] - 5 * 3600) < 1,
            str(session),
        )
        check("window tokens exclude the old one", session is not None and session["tokens"] == 2 * 15 + 500, str(session))
        check("claude starts with no cap set", r["claude"]["limits"] == {}, str(r["claude"]["limits"]))
        check("byDay covers seven days", len(week["byDay"]) == 7, str(len(week["byDay"])))

        limits = r["codex"]["limits"]
        check("codex reports its real percentage", limits and limits["usedPercent"] == 42.5, str(limits))
        check("codex reports the weekly window", limits and limits["windowMinutes"] == 10080, str(limits))
        check("codex plan comes through", limits and limits["plan"] == "pro", str(limits))

        # Appending must be picked up without re-reading what was already seen.
        offset_before = u._files[str(transcript)]["offset"]
        with transcript.open("a", encoding="utf-8") as fh:
            fh.write(claude_line(now - 60, 50))
        r2 = u.collect_usage()
        check("an appended message is counted", r2["claude"]["week"]["messages"] == 5, str(r2["claude"]["week"]["messages"]))
        check(
            "the file is read from where it stopped",
            u._files[str(transcript)]["offset"] > offset_before,
        )

        # A truncated file must not double count what is re-read.
        transcript.write_text(claude_line(now - 30, 70), encoding="utf-8")
        r3 = u.collect_usage()
        check("a rewritten file resets its tally", r3["claude"]["week"]["messages"] == 1, str(r3["claude"]["week"]["messages"]))

        # The newest message's input side is the context that request carried.
        ctx = r["claude"]["context"]
        check("context is the newest message", ctx is not None and ctx["model"] == "claude-opus-5", str(ctx))
        check("context sums the whole input side", ctx and ctx["tokens"] == 10 + 1000 + 5, str(ctx))
        check("context knows the model's window", ctx and ctx["window"] == 1_000_000, str(ctx))
        check(
            "context percent matches the window",
            ctx and abs(ctx["percent"] - 100 * 1015 / 1_000_000) < 0.05,
            str(ctx),
        )

        # A percentage needs a cap; without one there is nothing to report.
        check("no cap means no percentage", r["claude"]["week"]["percent"] is None)
        u.save_limits({"sessionTokens": 1000, "weekTokens": 2000})
        capped = u.collect_usage()["claude"]
        check("a cap turns spend into a percentage", capped["week"]["percent"] is not None, str(capped["week"]))
        check(
            "the percentage is measured against the cap",
            capped["week"]["percent"] == round(min(100.0, 100 * capped["week"]["billable"] / 2000), 1),
            str(capped["week"]),
        )
        check("a percentage never runs past full", capped["week"]["percent"] <= 100, str(capped["week"]))
        u.save_limits({"sessionTokens": 0, "weekTokens": 0})
        check("zero clears a cap", u.load_limits() == {}, str(u.load_limits()))

        # An old-only transcript leaves no window open.
        u._files.clear()
        transcript.write_text(claude_line(now - 9 * 3600, 100), encoding="utf-8")
        r4 = u.collect_usage()
        check("an expired window reports nothing", r4["claude"]["session"] is None, str(r4["claude"]["session"]))

        print(f"\n{_FAILURES} failure(s)")
        return 1 if _FAILURES else 0
    finally:
        os.environ.pop("CLAUDE_HOME", None)
        os.environ.pop("CODEX_HOME", None)
        os.environ.pop("CLICX_USAGE_LIMITS", None)
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
