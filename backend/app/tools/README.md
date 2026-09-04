# app/tools

The tool registry — the only path agent/LLM code has to touch business data. Every tool
independently validates its arguments and permissions regardless of what the LLM claims. Added
in Phase 4. See `docs/tools.md` and `docs/decisions.md` ADR-003.
