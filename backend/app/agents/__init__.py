"""Agent layer package. `run_agent` is the single entry point used by the
chat API; everything below it is LangGraph workflows on the tool registry.

Rule (ADR-003): code in this package never imports a SQLAlchemy session or
ORM model for data access — it only calls registry tools, which own
validation, permission checks and auditing.
"""

from app.agents.orchestrator import run_agent

__all__ = ["run_agent"]