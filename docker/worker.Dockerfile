# Build context is the repo root (see docker-compose.yml). Same image as the
# backend (same codebase + requirements) but starts the APScheduler worker
# process instead of uvicorn (docs/decisions.md ADR-007).
FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

CMD ["python", "-m", "app.worker.main"]