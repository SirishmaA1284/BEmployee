"""Proactive worker process (Phase 6, docs/decisions.md ADR-007).

Run with `python -m app.worker.main`. See `app/worker/main.py` for the
APScheduler jobs, and `app/services/worker_jobs.py` for the deterministic
check bodies they run.
"""