"""MCP package (Phase 7, docs/decisions.md ADR-010).

`server.py` exposes a minimal, read-only MCP server (JSON-RPC 2.0 over HTTP)
that re-exposes a small subset of the internal tool registry. See docs/mcp.md.
"""