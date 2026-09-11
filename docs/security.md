# Security

Status: implemented controls below are enforced in code and covered by tests; items under
"Production Hardening" remain roadmap. See `docs/threat-model.md` for the threat analysis this
implements, re-read against the built system at the end of Phase 8.

## Implemented Controls

- **AuthN:** bcrypt password hashing, short-lived JWT access tokens, and **rotating refresh
  tokens** (Phase 8): opaque tokens stored as SHA-256 hashes only; `POST /api/auth/refresh`
  rotates (revoke + reissue) and `POST /api/auth/logout` revokes. A replayed refresh token is
  rejected on second use.
- **AuthZ:** role (`OWNER`/`ADMIN`/`EMPLOYEE`) + business-membership scoping enforced
  server-side on every request; see `docs/authorization.md`.
- **Rate limiting (Phase 8 + Phase 9):** per-IP fixed-window limits on `/api/auth/register`,
  `/api/auth/login`, `/api/auth/refresh`, and `/api/agent/chat` (returns 429). Phase 9 makes it
  **distributed**: with `REDIS_URL` configured every API instance shares one counter budget via
  Redis (`INCR`+`EXPIRE`); `init_rate_limiter()` runs in the FastAPI lifespan and falls back to
  the in-process counter (with a logged warning) if Redis is unreachable, so a Redis outage
  never takes the API down. Tests run against the in-process backend.
- **Input validation:** Pydantic schemas on every API request and every tool input; no
  unvalidated data reaches the ORM.
- **SQL injection:** parameterized queries only, via SQLAlchemy ORM/Core — no raw string SQL
  concatenation.
- **CORS:** explicit allow-list of frontend origin(s) via environment configuration.
- **Secrets management:** environment variables only; `.env.example` documents required keys
  with no real values (spec §36).
- **File upload validation:** for document uploads (RAG, Phase 7 + Phase 9) — content-type
  allow-list (text/plain, text/markdown, text/csv, application/json, application/pdf, and
  DOCX) and a 2 MiB size limit, enforced in `backend/app/api/documents.py`. PDF/DOCX text is
  extracted by pinned, pure-Python parsers (`app/services/extraction.py`); parse failures are
  rejected with 422 and nothing is persisted. Virus scanning is a production-hardening item
  (not MVP-blocking).
- **RAG untrusted content:** retrieved chunks are injected into prompts only inside a delimited
  `<business_documents>` block labeled as reference data that can never introduce instructions
  (FR-23, see `docs/threat-model.md` T1).
- **Structured logging (FR-26):** request IDs on every HTTP request and workflow/session IDs
  on agent runs, emitted as key=value log lines (`app/core/logging.py`).
- **Prompt injection defenses:** see `docs/threat-model.md` T1.
- **Tool permission checks:** see `docs/tools.md` and `docs/decisions.md` ADR-003.
- **Audit logging:** every state-changing action, human or AI, per spec §13/25.

## Production Hardening (roadmap — not yet claimed)

Refresh-token rotation and the distributed (Redis) rate limiter are shipped; remaining
roadmap items: WAF/anomaly detection, secrets rotation automation, penetration testing,
SOC2-style controls, virus scanning of uploads, and email/password reset flows. These are
roadmap items, not silently skipped requirements.
