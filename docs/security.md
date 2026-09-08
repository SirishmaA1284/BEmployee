# Security

Status: design-level now; will be updated with concrete implementation details (libraries,
middleware, config) as Phases 2, 5, and 8 land. See `docs/threat-model.md` for the threat
analysis this implements.

## Planned Controls

- **AuthN:** bcrypt password hashing, short-lived JWT access tokens.
- **AuthZ:** role (`OWNER`/`ADMIN`/`EMPLOYEE`) + business-membership scoping enforced
  server-side on every request; see `docs/authorization.md`.
- **Input validation:** Pydantic schemas on every API request and every tool input; no
  unvalidated data reaches the ORM.
- **SQL injection:** parameterized queries only, via SQLAlchemy ORM/Core — no raw string SQL
  concatenation.
- **Rate limiting:** per-user/IP limits on auth endpoints and the AI employee endpoint
  (added Phase 8).
- **CORS:** explicit allow-list of frontend origin(s) via environment configuration.
- **Secrets management:** environment variables only; `.env.example` documents required keys
  with no real values (spec §36).
- **File upload validation:** for document uploads (RAG, Phase 7) — content-type allow-list
  (text/plain, text/markdown, text/csv, application/json) and a 2 MiB size limit, enforced in
  `backend/app/api/documents.py`. Virus scanning is a production-hardening item (not
  MVP-blocking).
- **RAG untrusted content:** retrieved chunks are injected into prompts only inside a delimited
  `<business_documents>` block labeled as reference data that can never introduce instructions
  (FR-23, see `docs/threat-model.md` T1).
- **Prompt injection defenses:** see `docs/threat-model.md` T1.
- **Tool permission checks:** see `docs/tools.md` and `docs/decisions.md` ADR-003.
- **Audit logging:** every state-changing action, human or AI, per spec §13/25.

## MVP vs. Production Hardening

Explicitly **not** claimed as production-ready at MVP: refresh-token rotation, WAF/anomaly
detection, secrets rotation automation, penetration testing, SOC2-style controls. These are
roadmap items, not silently skipped requirements.
