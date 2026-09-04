# MCP (Model Context Protocol)

Status: placeholder — MCP server ships in Phase 7 per `docs/decisions.md` ADR-010. The core
application does not depend on MCP being reachable.

Will cover: which tools are exposed externally (a deliberately small, mostly read-only subset
— see ADR-010), authentication for MCP clients, authorization mapping to the same
role/business-scoping used internally, error handling, and example MCP tool-call transcripts.
