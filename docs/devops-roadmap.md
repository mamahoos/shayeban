# DevOps Roadmap

> Part of the Shayeban architecture docs. Which roadmap tasks a
> DevOps-flavored contributor can own, in what order, and — just as
> important — which ops work is **not** justified yet. Nothing here is a
> mandate to do all of it; each item still has to win against its trigger.

## 1. Who this is for

A teammate whose strength is infrastructure (like `mamahoos`) picking up
work that is genuinely valuable to the project, without becoming a blocker
for feature work. The rule from `roadmap.md` §1 holds: ops tasks attach to
a phase that already produces behavior.

## 2. DevOps tasks by phase

| Phase | Tasks (owner tags from `roadmap.md` / `first-milestone.md`) |
|---|---|
| **M0** | T1 scaffold + toolchain · T2 settings/`.env.example` · T3 Compose + healthchecks + non-root image · T15 `ci.yml` gate (docs/lint/type/test + offline e2e) + demo runbook |
| **Phase 0** | Alembic-in-entrypoint hardening (idempotent re-runs) |
| **Phase 1** | Log-field convention review (`observability.md` §1 subset) so feature work doesn't invent its own |
| **Phase 3** | Fixture-recording helper for harness tests (record once, replay offline) — small, optional |
| **Phase 7** | CI job for offline eval as a *soft* gate (`evaluation.md` §5) — pairs with the `[mlops]` runner |
| **Phase 8** | `audit` + `build` + `smoke` CI jobs · dependency scan + pinned base images · logging audit vs `observability.md` §1 + `jq` demo runbook · `pg_dump` backup script **with a tested restore drill** · clean-clone reproducibility check |

Suggested picking order: **M0 tasks 1 → 2 → 3 → 15** first (they unblock
everyone), then stay on call for Phase 8, then the soft eval gate.

## 3. Deliberately not now (and the trigger)

| Skipped | Trigger to add |
|---|---|
| Metrics endpoint / Prometheus / Grafana | `jq` stops answering "is FAILED rate rising?" (`observability.md` §5) |
| Container image scanning (Trivy etc.) | images distributed beyond laptops (`devops.md` §4) |
| Coverage thresholds | first real test suite exists — pick a modest floor then (`devops.md` §4) |
| Self-hosted runners | queue times hurt (`devops.md` §4) |
| Traefik / TLS / edge rate limits | a demo must leave the laptop (`security.md` §10) |
| Centralized logging (Loki/Graylog) | `docker compose logs` loses the thread across processes (`future-evolution.md` §1) |
| Backup automation beyond a script | Postgres leaves the laptop (`future-evolution.md` §1) |
| Kubernetes / Terraform / ArgoCD | never by aesthetics — multi-host need first (`future-evolution.md` §1) |
| Deploy pipeline beyond `git pull && compose up` | there is something to deploy to (`devops.md` §4) |

## 4. Standing rules for this track

- Every ops task ships with the thing it protects working — no CI job for
  a nonexistent app (`devops.md` §4).
- Security-sensitive items follow `security.md` (secrets never in source or
  images; forks never see secrets).
- If a task here seems to require a skipped technology, the task is wrong —
  re-read the trigger table first (`roadmap.md` §13).
