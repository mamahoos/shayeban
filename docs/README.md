# Shayeban Architecture Documentation

Architecture docs for **Shayeban**, a Telegram-based claim/news fact-checking
system. The set describes the **desired MVP architecture**, is explicit about
what exists today, and marks every deliberate deferral.

> Status: documentation phase. The repository contains **no application code
> yet** — see [`architecture-gap-analysis.md`](architecture-gap-analysis.md)
> for current-vs-desired.

## Reading order

**Start reading → [00 · System overview](00-system-overview.md)** — every
document links to its predecessor, successor, and back to this index.

| # | Doc | Covers |
|---|---|---|
| 00 | [`00-system-overview.md`](00-system-overview.md) | Product surfaces, conceptual layer map (the numbering all docs reference), glossary |
| 01 | [`01-architecture.md`](01-architecture.md) | MVP shape: modular monolith, module map, boundaries, process/deploy shape |
| 02 | [`02-components.md`](02-components.md) | Component catalog, data contracts, dependency rules |
| 03 | [`03-investigation-lifecycle.md`](03-investigation-lifecycle.md) | End-to-end lifecycle, data flow, cache path, failure branches |
| 04 | [`04-fsm.md`](04-fsm.md) | Investigation state machine: states, transitions, invariants, restart policy |
| 05 | [`05-harness-and-news-ingestion.md`](05-harness-and-news-ingestion.md) | Harness: ingestion pipeline, source tiers, clustering, volatility/breaking mode, budgets |
| 06 | [`06-laya.md`](06-laya.md) | Laya: what it is, the three passes, serving modes, versioning |
| 07 | [`07-database-schema.md`](07-database-schema.md) | Postgres + pgvector schema, table notes, MVP deltas, indexing |
| 08 | [`08-evidence-and-source-weighting.md`](08-evidence-and-source-weighting.md) | Independence gate, tier weights, roll-up rules, virality invariants |
| — | [`architecture-gap-analysis.md`](architecture-gap-analysis.md) | Current → Desired MVP → Gap → Why it matters |

**Part 2 — engineering (DevOps/MLOps phase)**

| Doc | Covers |
|---|---|
| [`devops.md`](devops.md) | Toolchain, local workflow, the smallest useful CI gate, secrets in CI |
| [`deployment.md`](deployment.md) | Compose topology: containers, networks, volumes, health, migrations, dev workflow |
| [`mlops.md`](mlops.md) | Model/prompt/embedding/config versioning, provenance, change management |
| [`evaluation.md`](evaluation.md) | Eval targets, golden dataset design, runner, growth path |
| [`observability.md`](observability.md) | Structured log fields, investigation inspection, health, growth path |
| [`security.md`](security.md) | Trust boundaries, input threats, secrets, Docker/Actions hardening |
| [`future-evolution.md`](future-evolution.md) | MVP → Future → Trigger per subsystem, extension points, open questions |

**Part 3 — implementation planning**

| Doc | Covers |
|---|---|
| [`roadmap.md`](roadmap.md) | Nine phases, six milestones, task sets, GitHub structure |
| [`first-milestone.md`](first-milestone.md) | M0: the first vertical slice, 15 concrete tasks, demo DoD |
| [`devops-roadmap.md`](devops-roadmap.md) | Which tasks a DevOps contributor owns — and what is not justified yet |
| [`mlops-roadmap.md`](mlops-roadmap.md) | Which tasks an MLOps contributor owns — registry-less on purpose |

## Provenance

| Doc | Origin |
|---|---|
| `05-…` | Renumbered from the original `01-harness-and-news-ingestion.md` |
| `07-…` | Renumbered from the original `02-database-schema.md`, plus §4 MVP deltas |
| `01-…`, `observability.md`, `deployment.md` | Absorb the former `03-microservices-architecture.md` (monolith decision, module boundaries → 01; observability → observability.md; deployment → deployment.md), which was then removed |
| `devops.md`, `mlops.md`, `evaluation.md` | Split out of and supersedes the intermediate `10-devops-mlops.md` |
| `observability.md`, `security.md`, `future-evolution.md` | Renamed from the first-pass `09-…`, `11-…`, `12-…` and expanded for the DevOps/MLOps phase |
| `roadmap.md`, `first-milestone.md`, `devops-roadmap.md`, `mlops-roadmap.md` | New in the roadmap phase — implementation planning only |
| `00`–`04`, `06`, `08`, gap analysis | New in this doc set |
