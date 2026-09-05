"""Deterministic risk classification (docs/decisions.md ADR-004).

Phase 4 ships the classification *labels* the rest of the system records
(agent actions carry a risk level per FR-14) but not the approval engine —
that lands in Phase 5 with `business_policies`, thresholds and approval
requests (FR-16/FR-17/FR-18, ADR-015). Keep `classify_action` as the single
seam: Phase 5 replaces its body, not every call site.

Rule: the LLM proposes *what* to do; whether it is risky is decided here,
in plain Python, and cannot be short-circuited by prompt content.
"""

from __future__ import annotations

import enum
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.tools.base import ToolSpec


class RiskLevel(str, enum.Enum):
    """FR-17 risk classes. LOW executes automatically (Phase 5: MEDIUM is
    configurable per business, HIGH always requires human approval)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


def classify_action(tool: ToolSpec, arguments: dict) -> RiskLevel:
    """Returns the risk level for executing `tool` with `arguments`.

    Phase 4: a tool's declared risk level is the whole story — writes that
    change real business state (orders, purchase orders, inventory) are
    MEDIUM, reads are LOW, and nothing is HIGH until Phase 5 wires
    thresholds/policy rules that actually gate actions. `arguments` is
    accepted (and ignored) now so the Phase 5 signature is already stable.
    """
    return tool.risk_level