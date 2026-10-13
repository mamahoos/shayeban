# docker/Dockerfile — app image (deployment.md §2)
# One image, one process: FastAPI + aiogram + the entire pipeline, single asyncio loop.
# Build context is the repo root (compose sets `build: context: ..`).
#
# Intended shape (to be filled in, not decided here):
#   - base: python:3.12-slim (or the version pinned in devops.md)
#   - install deps from pyproject/lock
#   - copy the shayeban/ package
#   - entrypoint: run `alembic upgrade head`, then start the app (deployment.md §7)
