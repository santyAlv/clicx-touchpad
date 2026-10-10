"""ClicX minimal authorization abstraction (Fase 0).

IMPORTANT — preserve existing behaviour: ClicX today has no authentication, so the
default authorizer ALLOWS every connection (no change for existing clients). This
module only provides the *shape* (context per connection, checks by action) that
Fase 5 hardens into real PIN/trusted/revocation timeout. Nothing here must block
current connections or change how main.py / gui_app.py accept clients.

Classes in this module are pure data + pure functions (no I/O, no side effects) so
they are also easy to unit-test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AuthLevel(Enum):
    """Provisional authorization levels.

    ``ALLOW`` mirrors today: no checks, everything permitted (existing behaviour).
    Later phases lower the default and require verified devices at higher levels.
    """

    ALLOW = "allow"
    PAIRING = "pairing"  # device present but not yet trusted (reserved, Fase 5)
    BLOCK = "block"


class Action(Enum):
    """Categories of operations the authorizer can gate. Reserved for Fase 5."""

    POINTER = "pointer"
    INPUT = "input"
    READ = "read"
    CONTROL = "control"
    DANGEROUS = "dangerous"
    PRIVACY = "privacy"  # clipboard, screen, files


@dataclass
class ConnectionContext:
    """Per-connection authorization state.

    Created once per inbound WS connection. By default it mirrors the historical
    behaviour: fully authorized (``ALLOW``).
    """

    peer: str | None = None
    device_id: str | None = None
    level: AuthLevel = AuthLevel.ALLOW
    meta: dict[str, Any] = field(default_factory=dict)

    def is_authorized(self) -> bool:
        """True if this connection may act at all (today: always)."""
        return self.level is AuthLevel.ALLOW


@dataclass
class Decision:
    """Result of an authorization check."""

    allowed: bool
    reason: str = ""
    level: AuthLevel = AuthLevel.ALLOW

    @property
    def denied(self) -> bool:
        return not self.allowed


class Authorizer:
    """Stateless policy object.

    Holds per-action rules. In Fase 0 the only rule is: connections at ALLOW level may
    do everything; anything else is denied. Replace/extend in Fase 5 (PIN, trusted
    store, revocation, timeouts).
    """

    #: Default required level for each action category. Empty = no extra gate beyond
    #: ``is_authorized()``, preserving today's behaviour.
    _DEFAULT_REQUIRED: dict[Action, AuthLevel] = {}

    def __init__(self, required: dict[Action, AuthLevel] | None = None) -> None:
        self._required: dict[Action, AuthLevel] = (
            dict(required) if required is not None else dict(self._DEFAULT_REQUIRED)
        )

    def require(self, action: Action, level: AuthLevel) -> None:
        """Raise the required level for an action category. (Fase 5 uses this.)"""
        self._required[action] = level

    def check(
        self,
        ctx: ConnectionContext,
        action: Action,
        *,
        data: dict[str, Any] | None = None,
    ) -> Decision:
        """Authorize ``action`` for ``ctx``. ``data`` reserved for later payload checks.

        Preserves existing behaviour: today every connection is ALLOW and nothing is
        gated, so this always permits. Welcome to write nothing-dangerous logic here
        only when Fase 1/5 introduce gated actions.
        """
        if not ctx.is_authorized():
            return Decision(False, "connection is not authorized", ctx.level)

        required = self._required.get(action)
        if required is not None:
            # If the required level outranks the connection's, deny.
            if _RANK[required] > _RANK[ctx.level]:
                return Decision(False, f"requires {required.value}", ctx.level)

        return Decision(True, "allowed", ctx.level)


# Ordering for comparing AuthLevel values: higher rank = stricter requirement.
# Today BLOCK is lowest so nothing meaningful; grows meaning in Fase 5.
_RANK: dict[AuthLevel, int] = {
    AuthLevel.BLOCK: 0,
    AuthLevel.PAIRING: 1,
    AuthLevel.ALLOW: 2,
}
