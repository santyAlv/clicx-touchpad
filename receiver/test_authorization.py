"""Standalone tests for receiver/authorization.py (Fase 0).

Run:  python receiver/test_authorization.py
Exits 0 on success. No third-party deps.
Core invariant: existing behaviour is preserved — a connection at the default
(ALLOW) level is fully permitted.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from authorization import Action, AuthLevel, Authorizer, ConnectionContext  # noqa: E402

_FAILURES = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _FAILURES
    if not cond:
        _FAILURES += 1
        print(f"FAIL {name}  {detail}")
    else:
        print(f"ok   {name}")


def test_default_context_authorized():
    ctx = ConnectionContext(peer="127.0.0.1:1234")
    check("default ctx is_authorized", ctx.is_authorized() is True)


def test_default_authorizer_allows_all():
    ctx = ConnectionContext(peer="x")
    a = Authorizer()
    for act in Action:
        d = a.check(ctx, act)
        check(f"default allows {act.value}", d.allowed is True, d.reason)


def test_blocked_connection_denied():
    ctx = ConnectionContext(peer="x", level=AuthLevel.BLOCK)
    a = Authorizer()
    for act in Action:
        d = a.check(ctx, act)
        check(f"blocked denied {act.value}", d.denied is True, d.reason)


def test_required_level_gating():
    # Raise the gate for DANGEROUS; an ALLOW connection should still pass (in Fase 0
    # ALLOW is the top rank). A PAIRING connection must be denied.
    a = Authorizer()
    a.require(Action.DANGEROUS, AuthLevel.ALLOW)
    allow_ctx = ConnectionContext(peer="a", level=AuthLevel.ALLOW)
    check("ALLOW passes required-ALLOW", a.check(allow_ctx, Action.DANGEROUS).allowed)

    a2 = Authorizer()
    a2.require(Action.DANGEROUS, AuthLevel.ALLOW)
    pairing = ConnectionContext(peer="b", level=AuthLevel.PAIRING)
    d = a2.check(pairing, Action.DANGEROUS)
    check("PAIRING denied required-ALLOW", d.denied is True, d.reason)


def test_decision_shape():
    a = Authorizer()
    d = a.check(ConnectionContext(peer="x"), Action.READ)
    check("decision has allowed", d.allowed is True)
    check("decision has denied prop", d.denied is False)
    check("decision has reason", isinstance(d.reason, str))


def main() -> int:
    test_default_context_authorized()
    test_default_authorizer_allows_all()
    test_blocked_connection_denied()
    test_required_level_gating()
    test_decision_shape()
    print("\n---")
    print(f"{_FAILURES} failure(s)")
    return 1 if _FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
