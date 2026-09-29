# Implementation Roadmap

> Part of the Shayeban architecture docs. The incremental plan for building
> the MVP on top of this doc set: nine phases, six GitHub milestones, and one
> first vertical slice. Companion docs: `first-milestone.md` (the slice),
> `devops-roadmap.md` and `mlops-roadmap.md` (who owns which tasks).

## 1. How to read this roadmap

- **Vertical slices over layers.** Each phase ends in behavior a user (or a
  reviewer) can exercise — working feature + tests + basic observability +
  documentation beats isolated infrastructure work.
- **MVP discipline.** Only tasks needed for the slice or the phase are listed.
  Technologies are adopted when a measured need exists
  (`future-evolution.md` §1), never because they are industry standard.
- **Task sizing.** Every task is one engineer, one focused session
  (roughly S/M: 1–5 files). Anything bigger gets split before it becomes an
  issue.
- **Owner tags:** `[devops]` = well-suited to a DevOps/MLOps contributor,
  `[mlops]` = model/eval/registry-flavored, `[docs]` = documentation-only.
  Untagged = ordinary backend/feature work. `devops-roadmap.md` and
  `mlops-roadmap.md` collect these.
- **Backlog hygiene:** this document is the backlog for *later* phases. Only
  `M0` plus the tasks of the phase currently open become GitHub issues —
  nobody needs 40 open issues to know what comes next.

## 2. Milestone map

| Phase | GitHub milestone | Delivers | Opens when… |
|---|---|---|---|
| 0 + first slice | **M0 — Foundation & first slice** | `compose up` → inline query → verdict, end to end | now |
| 1 + 2 | **M1 — Telegram core & lifecycle** | both surfaces, quotas, complete FSM | M0 demo works |
| 3 | **M2 — Harness** | real retrieval: query → fetch → tiered evidence | M1 merged |
| 4 + 5 | **M3 — Laya & evidence engine** | real reasoning + invariant-tested weighting | M2 merged |
| 6 + 7 | **M4 — History, feedback & evaluation** | auditable verdicts, feedback, golden set | M3 merged |
| 8 | **M5 — DevOps polish** | justified CI/ops hardening | pipeline works end to end |

Phases describe *what* to build; `first-milestone.md` cuts a thin line
through phases 0–5 first, so the phase task lists below assume the slice
already exists (each phase notes its M0 overlap and what remains).

## 3. Phase 0 — Foundation

**Goal.** `git clone` → `docker compose up` → healthy app + migrated
database + green test on any teammate's laptop.

**Why.** Everything lands on this; "works on the author's machine" is the
portfolio-project killer. Toolchain choices are already made in the doc set:
uv, FastAPI + aiogram single process (`01-architecture.md`), Postgres +
Alembic, httpx / Trafilatura (`05-…`).

**Dependencies.** None.

**Tasks**

1. `[devops]` Scaffold: uv project, `src/shayeban/` layout, `pyproject`
   with `ruff` + `mypy --strict` + pytest configured.
2. Settings via `pydantic-settings`: `.env.example` (`BOT_TOKEN`,
   `SEARCH_API_KEY`, `DATABASE_URL`), fail-fast validation at startup
   (`security.md` §6).
3. `[devops]` Compose: `postgres` + `app`, non-root image, healthchecks,
   `GET /health` endpoint (`deployment.md` §2–§6).
4. Alembic wired to Compose; entrypoint runs migrations before the app
   starts (`deployment.md` §7).
5. `[devops]` `ci.yml` skeleton: `docs`, `lint`, `type`, `test` jobs
   (`devops.md` §4).

**Definition of done.** Fresh clone + `.env` → `docker compose up` →
`/health` returns 200 with no local Python setup; `uv run pytest` green
locally; CI green on a PR.

**Future extension.** `audit`/`build` CI jobs, smoke job, image publishing —
all in Phase 8.

## 4. Phase 1 — Telegram core

**Goal.** Inline mode and group messages both converge on **one**
`handle_claim()` entrypoint; the bot is usable from any chat.

**Why.** The gateway's biggest hazard is duplicated logic across surfaces
(`01-architecture.md` §3) — proving the shared path before the pipeline gets
complex is cheap insurance. Quotas exist from day one because they are
columns, not features (`07-database-schema.md`).

**Dependencies.** Phase 0.

**Tasks**

1. `bot_gateway`: aiogram inline-query handler builds `RawMessage` →
   calls `handle_claim()` → placeholder reply ("investigating…").
2. Group entry via `/factcheck` command + reply routed to the **same**
   `handle_claim()`; integration test asserts both surfaces hit one path.
3. Per-user daily quota check (`users.daily_quota_used`) before an
   investigation row is created.
4. Structured log per update: `investigation_id`, surface, language, quota
   remaining (subset of `observability.md` §1).
5. Detection hook point stubbed as a `detect(message) -> bool` port with a
   command-only implementation — Laya replaces it in Phase 4.

**Definition of done.** Inline query anywhere → placeholder response;
`/factcheck` in a group → same entrypoint (test-proven); quota decrements;
logs correlate by id.

**M0 overlap.** The slice ships task 1 + 2 (shared-entrypoint test) in thin
form; quotas, log fields, and the detection port land here.

**Future extension.** Per-message Laya detection gate (Phase 4), ack-and-edit
delivery (Q1), privacy modes (Q4).

## 5. Phase 2 — Investigation pipeline (FSM)

**Goal.** A persisted, tested state machine drives every investigation from
`RECEIVED` to a terminal state; restarts are honest.

**Why.** The FSM is the orchestration spine — without it, stage logic
scatters into handlers (`architecture-gap-analysis.md`).

**Dependencies.** Phase 0 (DB), Phase 1 (entrypoint).

**MVP state set (decision).** The designed FSM (`04-fsm.md` §1) minus
`CLUSTERING`: with semantic clustering and the verdict cache deferred
(embeddings are not chosen yet — `architecture-gap-analysis.md`),
`CLAIM_EXTRACTED → HARNESS_RUNNING` directly. Everything else stays —
including `VALIDATION` before `VERDICT` (Q5), `RETRYING`, and the terminal
set. Re-adding `CLUSTERING` later is a table change, not a redesign.

**Tasks**

1. FSM core: state enum, transition table, `transition()` that rejects
   illegal moves; invariant tests (exactly one state; only `investigation/`
   transitions — `04-fsm.md` §3).
2. Alembic migration for `investigations` (state, attempts, budget, claim
   text, language, timestamps, error — `07-database-schema.md` §4).
3. Orchestrator: async task per investigation; each transition persisted
   transactionally with the stage result (`04-fsm.md` §2).
4. Restart policy: startup marks stale non-terminal rows
   `FAILED (interrupted by restart)` (`04-fsm.md` §5) — with a test.
5. `[docs]` Sync `04-fsm.md` / `03-investigation-lifecycle.md` with the
   MVP-minus-`CLUSTERING` subset (mark the state deferred).

**Definition of done.** Stub stages carry a claim `RECEIVED → … → COMPLETED`;
`kill -9` mid-run → row marked `FAILED` on restart; every transition logged;
illegal-transition tests fail loudly.

**M0 overlap.** Tasks 1–4 ship in the slice (that *is* the slice's
skeleton).

**Future extension.** Resume-from-checkpoint, queue + workers, re-add
`CLUSTERING` — triggers in `future-evolution.md` §1.

## 6. Phase 3 — Harness

**Goal.** `query generation → search → fetch → extract → normalize →
EvidencePackage` with source metadata and basic (URL/content-hash) dedup.

**Why.** Retrieval quality bounds verdict quality, and this is the only part
that touches the outside world — the untrusted-content boundary (`security.md`
§2) lives here.

**Dependencies.** Phase 0 (config/budgets), Phase 2 (investigation context).
**Blocking decision first:** Q3 (search provider).

**Tasks**

1. Decide Q3 (provider, key, cost envelope); implement one `SearchProvider`
   behind a port (httpx).
2. Query generation v0: heuristics (claim keywords, fa/en variants) behind a
   `QueryGenerator` port — the Q2 model slots in later.
3. Fetcher: timeouts, byte caps, content-type checks, redirect limit, and
   per-investigation budget counters (4 queries × 5 fetches, `05-…` §6).
4. Extractor: Trafilatura primary, BeautifulSoup fallback; strip
   script/style at this single choke point → `EvidenceItem` (url, domain,
   fetch time, text).
5. Seed `sources` rows (~25 domains across tiers) + tier lookup at
   extraction; URL-normalization + content-hash dedup.
6. Tests on recorded HTML fixtures (no network in unit tests) + one
   `@live`-marked manual smoke test.

**Definition of done.** Claim → ≥3 tiered, deduped evidence items within
budget; script-injection fixture yields clean text; unit suite runs offline.

**M0 overlap.** The slice ships tasks 1–6 in thin form (heuristics queries,
one provider, no clustering).

**Future extension.** Semantic clustering + `CLUSTERING` state, near-dup
copy detection (feeds the independence gate), multi-provider failover,
sandboxed fetching — each with its trigger in `future-evolution.md` §1.

## 7. Phase 4 — Laya

**Goal.** Claim detection and evidence reasoning run through Laya behind the
`PredictRunner` port, with model metadata recorded on every investigation.

**Why.** Reasoning is the product's brain; a clean model/runtime boundary is
what lets the model change later without touching the pipeline
(`06-laya.md` §4).

**Dependencies.** Phase 2 (states), Phase 3 (evidence), the existing
`laya-lab` adapter (`PredictRunner`, `FakeRunner`).

**Tasks**

1. `decision/` port: `PredictRunner` Protocol + in-process implementation
   wrapping the pinned checkpoint; port `FakeRunner` for tests.
2. Detection pass: wire the Phase-1 `detect()` stub to Laya — group gate
   before `RECEIVED`, detection inside `CLASSIFYING` (`04-fsm.md` §4).
3. Stance pass at `LAYA_ANALYSIS`: per-evidence stance + confidence.
4. Verdict pass at `VERDICT`: schema-constrained output; record
   `laya_version`, `laya_checkpoint`, `question_schema_version` on the row
   (`mlops.md` §3.1).
5. Config: checkpoint pinned in settings; startup fails fast with a clear
   message when weights are absent.

**Definition of done.** Offline e2e test with `FakeRunner` reaches
`COMPLETED`; one real local run produces a verdict; the investigation row
carries model + schema versions.

**M0 overlap.** Tasks 1 and 4 (recording) are slice tasks; 2–3 ship in M1/M3
order — the slice runs stance + verdict with the real checkpoint and leaves
group detection to M1.

**Future extension.** `laya.serve` split, second generative model (Q2),
calibration eval — triggers in `future-evolution.md` §1.

## 8. Phase 5 — Evidence engine

**Goal.** First version of source weights, evidence weights,
corroboration/contradiction, recency, and source independence —
understandable, deterministic, invariant-tested.

**Why.** Establish the architecture (independence gate, tier weights,
validation guard), not a perfect scoring algorithm: "viral ≠ true" and
"copies ≠ corroboration" are correctness properties, not tuning targets
(`08-evidence-and-source-weighting.md`).

**Dependencies.** Phase 3 (evidence + source metadata), Phase 4
(stances/confidences).

**Tasks**

1. `config/weights.toml`: tier weights, confidence mapping, recency decay,
   thresholds — hashed as `config_version` (`mlops.md` §3.4).
2. `weighting/`: domain-level independence gate (group evidence by domain,
   cap each group's contribution), tier × confidence × recency roll-up →
   `VerdictCandidate` + strength (`08-…` §2–§3).
3. `validation/`: rule guard (evidence sufficiency, independence met,
   budget state) → allowed verdict set or `NEEDS_REVIEW` (`04-fsm.md` §4).
4. Record per-stance weighted contributions for the explanation templates.
5. Invariant test suite (10–15 table-driven scenarios: one source × 5
   copies doesn't confirm; contradiction forces UNCLEAR/NEEDS_REVIEW) —
   doubles as the first `eval/golden/weighting.jsonl` seed.

**Definition of done.** Fixture scenarios yield expected verdict classes;
the formula is documented in `08-…`; implementation and doc agree.

**M0 overlap.** A thin weighting v0 (same shape, fewer knobs) is a slice
task; this phase hardens it to the invariant suite.

**Future extension.** Learned weights from feedback, per-topic thresholds,
embedding-based copy detection — `future-evolution.md` §1.

## 9. Phase 6 — Database / history / feedback

**Goal.** Claims, sources, evidence, investigations, verdicts, and feedback
persisted so **every verdict is auditable** back to source URLs; feedback is
captured; `shayeban inspect <id>` exists.

**Why.** Auditing is a product trust property (`00-system-overview.md`
invariants) and the input to every later tuning effort. Note: persistence is
*not* postponed to this phase — tables land when first needed (P0
migrations, P1 users, P2 investigations, P3 evidence/sources, P5 verdicts);
Phase 6 is the completeness + feedback pass. `clusters` stays deferred with
clustering (Phase 3 future).

**Dependencies.** Phases 2–5 for the data to exist.

**Tasks**

1. Audit-schema pass: FK chain claim → evidence (with provenance) →
   verdict → explanation complete; migration + repository tests
   (`07-database-schema.md`).
2. Feedback capture: 👍/👎 inline keyboard on the verdict message →
   `feedback` row (`reviewed = false`).
3. `shayeban inspect <id>` CLI: state history, evidence, weights used,
   final verdict — the mechanism promised in `observability.md` §2.
4. Source history: update `sources.times_used` / `last_seen` on evidence
   insert — counters only, no scoring.
5. `[docs]` Decide + document raw-message retention (open item,
   `security.md` §9) with a minimal purge script.

**Definition of done.** Given an id, the full chain (verdict → evidence →
source URL) is queryable; feedback rows appear for verdict messages;
retention decision recorded.

**Future extension.** Review queue UI, feedback → eval cases, feedback →
weight tuning.

## 10. Phase 7 — Evaluation + MLOps

**Goal.** Golden dataset, repeatable evaluation, model/prompt/config version
tracking, and run artifacts — all runnable locally, with a soft CI job
where useful.

**Why.** After Phases 4–5, every prompt/threshold change becomes otherwise
unmeasurable opinion (`evaluation.md` §1).

**Dependencies.** Phases 4–5 (something to evaluate); designs in
`mlops.md` + `evaluation.md`.

**Tasks**

1. Seed `eval/golden/` — 30–50 hand-verified items across detection /
   stance / verdict / weighting, Persian + English, with `MANIFEST.md`
   (`evaluation.md` §3).
2. `[mlops]` `eval/run.py` runner: offline mode first (weighting, FSM,
   templates), then model mode (`evaluation.md` §4).
3. `[mlops]` Version pins in every run — git sha, checkpoint,
   question-schema, config hash — plus a row in `eval/RESULTS.md`
   (`mlops.md` §8).
4. `[mlops]` Verify inference metadata lands on live investigations
   (Phase 4 task 4) and on eval model-mode runs.
5. `[devops][mlops]` CI job: offline eval as a **soft gate** (report on the
   PR, don't block) once CPU runtime is measured (`evaluation.md` §5).

**Definition of done.** `uv run python eval/run.py --mode offline` emits
JSON + a RESULTS row; a PR shows the report; dataset lives in git with a
manifest.

**M0 overlap.** None (intentionally — measure after there is something to
measure).

**Future extension.** Model mode in CI, scheduled live runs, held-out split,
model registry — triggers in `mlops.md` §7.

## 11. Phase 8 — DevOps polish

**Goal.** Only after the pipeline works: CI/ops improvements that protect
real behavior — not before.

**Why.** Ops work without a working system produces green noise
(`devops.md` §4 closing note).

**Dependencies.** Phases 1–7 (behavior to protect); Phase 0 skeleton
deepened, not rebuilt.

**Tasks** (detail and selection guidance in `devops-roadmap.md`)

1. `[devops]` Complete the CI gate: `audit` + `build` jobs + `smoke`
   (compose up → health → FakeRunner pipeline) (`devops.md` §4).
2. `[devops]` Dependency vulnerability scan + pinned base images
   (`security.md` §7).
3. `[devops]` Structured-logging audit against `observability.md` §1 +
   demo runbook of `jq` recipes.
4. `[devops]` Backup/restore: `pg_dump` script + a **tested** restore drill,
   documented.
5. `[devops]` Reproducibility check: clean-clone CI build proves lockfile +
   pinned images (`mlops.md` §3.2).

**Definition of done.** Red lint/type/test/audit blocks merge; restore drill
run once and written down; demo works from a fresh clone.

**Future extension.** Metrics stack, container scanning, Traefik + TLS,
centralized logs — each gated by a trigger (`future-evolution.md` §1,
`devops.md` §4 skipped table).

## 12. GitHub structure

**Milestones** — the six from §2, nothing more. Closing a milestone is a
demo, not a date.

**Labels** — reuse what exists; add nine, no more:

| Keep (exist today) | Add | Purpose |
|---|---|---|
| `bug`, `enhancement`, `documentation` | `type/refactor`, `type/infra` | type vocabulary (`enhancement` = feature, `documentation` = docs — no duplicate `type/feature`/`type/docs`) |
| — | `area/backend`, `area/ai`, `area/harness`, `area/database`, `area/devops`, `area/mlops`, `area/docs` | who to ping / filter |

(Skip `good first issue` until M0 tasks land — then tag the XS ones.)

**Issue naming.** `<area>: <imperative summary>`, e.g.
`harness: fetch top-5 results with byte caps and timeouts`. Defects:
`<area>: <symptom>`. Area duplicates the `area/*` label on purpose — titles
are what notifications show. Milestone carries the phase; no phase prefix in
the title.

**Project board.** One GitHub Projects v2 board, four columns:
`Todo → In progress → In review → Done`, grouped by milestone. Automation:
PR opened → `In review`. No custom fields until the board itself feels
insufficient.

**Issue creation rule.** Issues are created for M0 now and for the next
phase when it opens — the later phases live in this document until then.

## 13. What we are explicitly not building

Kafka/Airflow/MLflow/Redis/Kubernetes/Terraform/ArgoCD, microservices,
distributed tracing, Prometheus/Grafana, model registry, queues — each with
its documented trigger in `future-evolution.md` §1, `mlops.md` §7, and
`devops.md` §4. If a task in this roadmap ever needs one of them to be
completed, that is a signal to stop and re-read the trigger table first.
