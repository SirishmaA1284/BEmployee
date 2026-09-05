# app/policies

Deterministic policy/risk rules (docs/decisions.md ADR-004) — the LLM proposes *what* to do;
whether it's risky is decided here in plain Python.

Phase 4 ships the risk labels (`app/policies/risk.py`): every registry tool declares a risk
level (LOW for reads, MEDIUM for writes) recorded on every `agent_actions` row. The full
policy engine — `business_policies` thresholds, MEDIUM-configurability, HIGH-always-approval,
approval requests — lands in Phase 5 behind the same `classify_action` function.