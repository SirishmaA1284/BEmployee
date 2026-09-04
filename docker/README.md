# docker

Dockerfiles for the backend, frontend, and worker images (added in Phase 2). The database
service is defined directly in the root `docker-compose.yml` using the official
`pgvector/pgvector` image, so it needs no Dockerfile of its own.
