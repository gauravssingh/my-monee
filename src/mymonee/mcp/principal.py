"""Agent execution principal and scope definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal


@dataclass(frozen=True)
class AgentPrincipal:
    """Security principal representing the caller of the Agent Service.

    The principal is established at process startup and carried into every
    Agent Service call. It must NEVER be accepted as an MCP tool parameter.
    """

    profile: str = "default"
    actor: str = "hermes"
    role: Literal["reader"] = "reader"
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def is_authorized(self) -> bool:
        """Check if the principal has valid read privileges."""
        return self.role == "reader" and bool(self.profile)


def create_agent_principal(
    profile: str = "default",
    actor: str = "hermes",
) -> AgentPrincipal:
    """Factory to create a frozen, process-scoped AgentPrincipal."""
    return AgentPrincipal(
        profile=profile.strip() or "default",
        actor=actor.strip() or "hermes",
        role="reader",
    )
