# Deployment

> Part of the Shayeban architecture docs. The local-first deployment design:
> containers, networks, volumes, environment and secrets, health checks,
> startup order, database initialization, migrations, and the developer
> workflow. Everything here must run on a laptop — `git clone` →
> `docker compose up`. Companion docs: `devops.md` (CI/toolchain),
> `mlops.md` (versioning), `observability.md` (signals).

## 1. Principles

- **One command, one host**: `docker compose up` on a laptop is the entire
  deployment. No production server, no orchestrator, no cloud.
- **Everything the system needs is in the compose file** — a teammate clones
  and gets the same stack (same images, same env, same init) as everyone else.
- **Nothing runs on the host except Docker itself.** Host-specific setup is
  limited to: Docker + Compose, a `.env` file, and (for model work) an NVIDIA
  runtime if a GPU is available.

## 2. Containers (MVP)

| Service | Image | Role | Notes |
|---|---|---|---|
| `app` | built from repo (`Dockerfile`) | FastAPI + aiogram + entire pipeline, single asyncio process | entrypoint runs migrations, then starts the app (§7) |
| `postgres` | `pgvector/pgvector:pg16` | primary datastore | official image; init script mounts into `/docker-entrypoint-initdb.d` |

| Deferred container | Trigger (see `future-evolution.md`) |
|---|---|
| `laya-service` (upstream `laya.serve`) | weight-loading/GPU contention measured in stage timings (`01-architecture.md` §4.2) |
| `traefik` | a demo must be reachable beyond the laptop/home LAN |
| `redis`, workers, brokers | measured single-process limits (see `future-evolution.md`) |

## 3. Networks

- One user-defined bridge network (`shayeban` internal).
- **No service publishes a port by default.** Debug access to the app API or
  Postgres happens by temporarily adding a `127.0.0.1:<port>:<port>` mapping
  — explicitly local, never `0.0.0.0`.
- Telegram and search APIs are reached **outbound only** (egress); nothing
  listens on the host. The `laya-service` (when added) joins the same
  internal network with no published port.

## 4. Volumes

| Volume | Mount | Purpose |
|---|---|---|
| `pgdata` | `postgres:/var/lib/postgresql/data` | durable history, clusters, evidence |
| `hf-cache` *(deferred)* | model weights cache for `laya-service` | so model downloads survive container recreation |

Backup: a host-side `pg_dump` cron/systemd-timer (documented in the repo
runbook when the first real users appear). Tear-down: `docker compose down`
keeps data; `down -v` destroys it — loud warning in `CONTRIBUTING.md`.

## 5. Environment configuration & secrets

```
.env            # git-ignored; per-developer values
.env.example    # committed; every required key with a safe placeholder
```

| Key | Purpose |
|---|---|
| `BOT_TOKEN` | Telegram bot token |
| `DATABASE_URL` | Postgres DSN (compose sets the default; override only for exotic setups) |
| `SEARCH_API_KEY` / `SEARCH_API_BASE` | search provider credentials |
| `TELEGRAM_TO` / `TELEGRAM_TOKEN` | CI notifications — GitHub **secrets**, never in `.env` for the app |
| `LAYA_DEVICE`, `LAYA_PRELOAD`, … | model runtime — only relevant once `laya-service` exists |

Rules: the app never reads secrets from anywhere but the environment; typed
settings validate required keys at startup and fail fast with a clear error;
`.env` is covered by `.gitignore` from day one (this repo currently has no
`.gitignore` — adding one is part of the scaffold, see gap analysis).

## 6. Health checks & startup dependencies

| Service | Check | Used for |
|---|---|---|
| `postgres` | `pg_isready -U …` (compose `healthcheck`) | `app` waits via `depends_on: condition: service_healthy` |
| `app` | `GET /health` (process + DB reachability) | compose health status; later: model reachability when split |

Startup order: `postgres` healthy → `app` runs migrations → `app` starts
listening (bot polling + API). The app **fails fast** (non-zero exit) if the
DB is unreachable after a bounded wait or if required env keys are missing —
a container that starts "green" while broken is worse than one that restarts
loudly.

## 7. Database initialization & migrations

| Layer | Mechanism |
|---|---|
| One-time init | SQL init script mounted into the Postgres entrypoint: `CREATE EXTENSION IF NOT EXISTS vector;` (and nothing else) |
| Schema evolution | **Alembic** — the `app` entrypoint runs `alembic upgrade head` before starting the server; migrations are forward-only for the MVP |
| Data migrations | rare, explicit (e.g. re-embedding all clusters after an embedding-model change — `mlops.md` §3) |

No schema DDL outside Alembic after the initial migration — otherwise laptops
diverge and "works on mine" becomes untraceable.

## 8. Local development workflow

```bash
git clone git@github.com:mamahoos/shayeban.git && cd shayeban
cp .env.example .env          # fill BOT_TOKEN / SEARCH_API_KEY
docker compose up --build     # postgres healthy → migrations → app
docker compose logs -f app    # structured JSON logs (observability.md)
docker compose down           # stop, keep data
```

Two modes, one compose file:

| Mode | How | Use |
|---|---|---|
| Full stack (default) | `docker compose up` | demos, integration smoke, "does it actually run" |
| Editable dev | run the app on the host (venv) against compose Postgres (`docker compose up postgres`) | fast iteration without image rebuilds |

Unit tests, lint, and typecheck never need Docker (pure logic + fakes —
`02-components.md`); Docker is only for the integrated stack.

## 9. Explicitly not deployed

Redis, message queues, Kubernetes, reverse proxies, managed databases,
monitoring stacks, CI runners beyond GitHub-hosted — each with a named
trigger in `future-evolution.md`. Deployment complexity must be pulled in by
measured need, not by aesthetics.
