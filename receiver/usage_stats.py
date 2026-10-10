"""Claude and Codex usage, read off the transcripts they already write locally.

Both CLIs append JSONL as they work:

  * Claude Code — ``~/.claude/projects/<slug>/<session>.jsonl``, one record per
    message, carrying a timestamp, the model and the full token counts.
  * Codex — ``~/.codex/sessions/<y>/<m>/<d>/rollout-*.jsonl``, which besides the
    conversation carries ``token_count`` events holding the API's own
    ``rate_limits``: percent used, window length and reset time.

So Codex can report a real percentage of its limit and Claude cannot: nothing on
disk says what the account's cap is, only what was spent. This module reports
what each one actually knows rather than inventing a number for the other.

The files are append-only, and together they run to tens of megabytes, so each
is read from where the last pass stopped instead of from the top.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

WEEK_SECONDS = 7 * 24 * 3600
# Context windows per model family. The transcript names the model, and the
# newest message's input side is the context that request actually carried.
CONTEXT_WINDOWS = {
    "opus-5": 1_000_000,
    "sonnet-5": 1_000_000,
    "fable-5": 1_000_000,
    "haiku-4-5": 200_000,
}
DEFAULT_CONTEXT_WINDOW = 200_000
# Anthropic's usage window is five hours long, starting with the first message
# that falls outside the previous one.
SESSION_SECONDS = 5 * 3600


def claude_root() -> Path:
    return Path(os.environ.get("CLAUDE_HOME") or (Path.home() / ".claude")) / "projects"


def codex_root() -> Path:
    return Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex")) / "sessions"


# --- incremental reading -----------------------------------------------------

# path -> {"offset": int, "events": [(ts, tokens)], "limits": dict | None}
_files: dict[str, dict[str, Any]] = {}


def _parse_ts(raw: Any) -> float | None:
    """Epoch seconds from an ISO-8601 stamp, or None if it is not one."""
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _new_lines(path: Path) -> Iterator[str]:
    """Lines appended since the last pass. A shrunk file is read from the top."""
    key = str(path)
    state = _files.setdefault(key, {"offset": 0, "events": [], "limits": None})
    try:
        size = path.stat().st_size
    except OSError:
        return
    if size < state["offset"]:  # rotated or rewritten
        state["offset"] = 0
        state["events"] = []
        state["limits"] = None
    if size == state["offset"]:
        return
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            fh.seek(state["offset"])
            for line in fh:
                if not line.endswith("\n"):
                    # A half-written last line: leave it for the next pass.
                    break
                state["offset"] += len(line.encode("utf-8", "replace"))
                yield line
    except OSError:
        return


def _record_event(path: Path, ts: float | None, tokens: dict[str, int], model: str) -> None:
    if ts is None:
        return
    _files[str(path)]["events"].append((ts, tokens, model))


# --- Claude ------------------------------------------------------------------

def _claude_tokens(usage: dict[str, Any]) -> dict[str, int]:
    def n(key: str) -> int:
        value = usage.get(key)
        return int(value) if isinstance(value, (int, float)) else 0

    return {
        "input": n("input_tokens"),
        "output": n("output_tokens"),
        "cacheRead": n("cache_read_input_tokens"),
        "cacheWrite": n("cache_creation_input_tokens"),
    }


def _scan_claude() -> None:
    root = claude_root()
    if not root.is_dir():
        return
    for path in root.glob("*/*.jsonl"):
        for line in _new_lines(path):
            if '"usage"' not in line:
                continue
            try:
                data = json.loads(line)
            except ValueError:
                continue
            message = data.get("message")
            if not isinstance(message, dict):
                continue
            usage = message.get("usage")
            if not isinstance(usage, dict):
                continue
            _record_event(
                path,
                _parse_ts(data.get("timestamp")),
                _claude_tokens(usage),
                str(message.get("model") or ""),
            )


# --- Codex -------------------------------------------------------------------

def _scan_codex() -> None:
    root = codex_root()
    if not root.is_dir():
        return
    for path in root.glob("**/*.jsonl"):
        for line in _new_lines(path):
            if '"token_count"' not in line:
                continue
            try:
                data = json.loads(line)
            except ValueError:
                continue
            payload = data.get("payload")
            if not isinstance(payload, dict) or payload.get("type") != "token_count":
                continue
            ts = _parse_ts(data.get("timestamp"))
            limits = payload.get("rate_limits")
            if isinstance(limits, dict):
                _files[str(path)]["limits"] = (ts or 0.0, limits)
            info = payload.get("info")
            if isinstance(info, dict):
                total = info.get("total_token_usage")
                if isinstance(total, dict):
                    _record_event(
                        path,
                        ts,
                        {
                            "input": int(total.get("input_tokens") or 0),
                            "output": int(total.get("output_tokens") or 0),
                            "cacheRead": int(total.get("cached_input_tokens") or 0),
                            "cacheWrite": 0,
                        },
                        "codex",
                    )


# --- aggregation -------------------------------------------------------------

def _events_for(prefix: Path) -> list[tuple[float, dict[str, int], str]]:
    root = str(prefix)
    events: list[tuple[float, dict[str, int], str]] = []
    for key, state in _files.items():
        if key.startswith(root):
            events.extend(state["events"])
    events.sort(key=lambda e: e[0])
    return events


def _prune(cutoff: float) -> None:
    """Drop anything older than the reporting window so memory stays bounded."""
    for state in _files.values():
        events = state["events"]
        if events and events[0][0] < cutoff:
            state["events"] = [e for e in events if e[0] >= cutoff]


def _sum(events: list[tuple[float, dict[str, int], str]]) -> dict[str, int]:
    totals = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}
    for _ts, tokens, _model in events:
        for key in totals:
            totals[key] += tokens.get(key, 0)
    return totals


def _billable(tokens: dict[str, int]) -> int:
    """Cache reads are the cheap part; the headline number leaves them out."""
    return tokens["input"] + tokens["output"] + tokens["cacheWrite"]


def _by_day(events: list[tuple[float, dict[str, int], str]], now: float) -> list[dict[str, Any]]:
    days: dict[str, int] = {}
    for ts, tokens, _model in events:
        day = datetime.fromtimestamp(ts, timezone.utc).astimezone().strftime("%Y-%m-%d")
        days[day] = days.get(day, 0) + _billable(tokens)
    out = []
    for back in range(6, -1, -1):
        day = datetime.fromtimestamp(now - back * 86400).astimezone().strftime("%Y-%m-%d")
        out.append({"day": day, "tokens": days.get(day, 0)})
    return out


def _current_window(
    events: list[tuple[float, dict[str, int], str]], now: float
) -> dict[str, Any] | None:
    """The five-hour window in progress, or None once it has expired.

    A window opens on the first message that falls outside the previous one, so
    walking the messages in order and starting a new window whenever one lands
    past the current window's end reproduces what the CLI is counting against.
    """
    start: float | None = None
    inside: list[tuple[float, dict[str, int], str]] = []
    for event in events:
        ts = event[0]
        if start is None or ts - start >= SESSION_SECONDS:
            start = ts
            inside = [event]
        else:
            inside.append(event)
    if start is None or now - start >= SESSION_SECONDS:
        return None
    return {
        "startedAt": start,
        "resetsAt": start + SESSION_SECONDS,
        "messages": len(inside),
        "tokens": _billable(_sum(inside)),
    }


def _models(events: list[tuple[float, dict[str, int], str]]) -> list[dict[str, Any]]:
    per: dict[str, int] = {}
    for _ts, tokens, model in events:
        if not model:
            continue
        per[model] = per.get(model, 0) + _billable(tokens)
    ranked = sorted(per.items(), key=lambda kv: kv[1], reverse=True)
    return [{"model": m, "tokens": t} for m, t in ranked[:4] if t > 0]


def _codex_limits(now: float) -> dict[str, Any] | None:
    """The newest rate-limit snapshot Codex recorded, whichever file it is in."""
    best: tuple[float, dict[str, Any]] | None = None
    root = str(codex_root())
    for key, state in _files.items():
        if not key.startswith(root):
            continue
        snapshot = state.get("limits")
        if snapshot and (best is None or snapshot[0] > best[0]):
            best = snapshot
    if best is None:
        return None
    seen_at, limits = best
    window = limits.get("primary")
    out: dict[str, Any] = {"plan": limits.get("plan_type"), "seenAt": seen_at}
    if isinstance(window, dict):
        out["usedPercent"] = window.get("used_percent")
        out["windowMinutes"] = window.get("window_minutes")
        out["resetsAt"] = window.get("resets_at")
    return out


def _context_window(model: str) -> int:
    for family, size in CONTEXT_WINDOWS.items():
        if family in model:
            return size
    return DEFAULT_CONTEXT_WINDOW


def _context(events: list[tuple[float, dict[str, int], str]]) -> dict[str, Any] | None:
    """How full the newest request's context was.

    A request carries its whole context on the input side — fresh input, what
    was read from cache and what it just wrote there — so the last message's
    input total is the context in use, the same number the CLI shows.
    """
    if not events:
        return None
    ts, tokens, model = events[-1]
    used = tokens["input"] + tokens["cacheRead"] + tokens["cacheWrite"]
    window = _context_window(model)
    return {
        "at": ts,
        "model": model,
        "tokens": used,
        "window": window,
        "percent": round(100 * used / window, 1) if window else None,
    }


def limits_path() -> Path:
    override = os.environ.get("CLICX_USAGE_LIMITS")
    if override:
        return Path(override)
    import deck_store

    return deck_store.config_dir() / "usage_limits.json"


def load_limits() -> dict[str, Any]:
    """Caps the user set, if any.

    Claude reports no cap of its own: the CLI reads its percentages live from
    the API and never writes them down, so a percentage here can only come from
    a number the user supplies. Without one the screen shows spend, not a
    fraction of something unknown.
    """
    try:
        raw = json.loads(limits_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def save_limits(values: dict[str, Any]) -> dict[str, Any]:
    current = load_limits()
    for key in ("sessionTokens", "weekTokens"):
        if key in values:
            value = values[key]
            if value in (None, 0, ""):
                current.pop(key, None)
            elif isinstance(value, (int, float)) and value > 0:
                current[key] = int(value)
    path = limits_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def _against(used: int, cap: Any) -> float | None:
    if not isinstance(cap, (int, float)) or cap <= 0:
        return None
    return round(min(100.0, 100 * used / cap), 1)


def collect_usage() -> dict[str, Any]:
    """Weekly totals and the session window for both CLIs. Counts only.

    Nothing here reads message content: only timestamps, model names and the
    token counters the tools record themselves.
    """
    now = time.time()
    _scan_claude()
    _scan_codex()
    _prune(now - WEEK_SECONDS)

    claude_events = _events_for(claude_root())
    codex_events = _events_for(codex_root())

    claude_week = _sum(claude_events)
    codex_week = _sum(codex_events)
    limits = load_limits()
    session = _current_window(claude_events, now)
    week_billable = _billable(claude_week)
    if session is not None:
        session["cap"] = limits.get("sessionTokens")
        session["percent"] = _against(session["tokens"], limits.get("sessionTokens"))

    return {
        "at": now,
        "claude": {
            "week": {
                "tokens": claude_week,
                "billable": week_billable,
                "messages": len(claude_events),
                "byDay": _by_day(claude_events, now),
                "cap": limits.get("weekTokens"),
                "percent": _against(week_billable, limits.get("weekTokens")),
            },
            "session": session,
            "context": _context(claude_events),
            "models": _models(claude_events),
            # The CLI reads its percentages live and writes none of them down,
            # so any fraction here comes from a cap the user set.
            "limits": limits,
        },
        "codex": {
            "week": {
                "tokens": codex_week,
                "billable": _billable(codex_week),
                "messages": len(codex_events),
                "byDay": _by_day(codex_events, now),
            },
            "limits": _codex_limits(now),
            "hasLimit": True,
        },
    }


def handle_usage(data: dict[str, Any]) -> dict[str, Any]:
    """Dispatcher entry for ``{"t": "usage"}``.

    ``{"t": "usage", "action": "limits", "sessionTokens": N, "weekTokens": N}``
    stores the caps the percentages are measured against; sending 0 clears one.
    """
    if data.get("action") == "limits":
        save_limits(data)
    return {"t": "usage", **collect_usage()}
