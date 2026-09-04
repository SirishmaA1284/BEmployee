# Tools

Status: placeholder — populated in Phase 4 with the full tool registry once implemented.

Will cover, per tool: name, description (as given to the LLM), input schema, output schema,
required permission/role, risk level, validation performed independently of LLM output, error
modes, and the audit event it writes. See `docs/architecture.md` §8 for the tool contract and
`docs/decisions.md` ADR-003 for why tools are the only DB access path reachable from agent code.
