"""Tool registry package.

Importing `app.tools` (or anything under it) registers the catalog on
`app.tools.registry.registry`, so the agents layer can rely on every tool
being present after a single import.
"""

from app.tools import catalog as _catalog  # noqa: F401 — registers tools on import
from app.tools.base import ToolError, ToolSpec
from app.tools.registry import ToolRegistry, registry

__all__ = ["ToolError", "ToolSpec", "ToolRegistry", "registry"]