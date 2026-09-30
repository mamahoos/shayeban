# First Milestone — M0: One Claim, One Verdict

> Part of the Shayeban architecture docs. The first small **vertical slice**
> to actually implement: everything the architecture promises, in the
> thinnest form that still proves the chain end to end. This is the only
> phase of `roadmap.md` that is fully specified as tasks — the rest stays
> high-level until its phase opens.

## 1. Goal

A user types `@shayeban_bot <some claim>` in any Telegram chat and receives a
verdict message with citations — through the **real** pipeline path:

```
Telegram → claim → investigation (FSM) → harness → evidence → Laya reasoning → verdict → reply
```

Even if each stage is intentionally simple. The slice is successful when a
reviewer can watch it happen and when CI proves it without the network.

## 2. Why this slice

- **Proves the architecture, not a demo script.** If the thin version fits
  the module boundaries (`01-architecture.md`), the full version will too.
- **Creates the integration test we design against:** one FakeRunner e2e
  test that every later phase must keep green.
- **De-risks the two scariest dependencies first:** the search provider (Q3)
  and the Laya checkpoint — both behind ports, both swappable.

## 3. Scope

| In the slice | Out of the slice (comes later) |
|---|---|
| Inline mode, live | Group per-message Laya detection (M1 — command entry only) |
| FSM = designed states **minus `CLUSTERING`** (`roadmap.md` §5) | Clustering, verdict cache, resume-from-checkpoint |
| Heuristic query generation (fa + en) behind a port | Generative query model (Q2) |
| One search provider behind a port (Q3 decided now) | Multi-provider failover |
| Fetch → extract → tier → URL/hash dedup, budget-capped | Embedding dedup, near-dup copy detection |
| Laya stance + verdict passes in-process (pinned checkpoint) | `laya.serve` split, detection gate for groups |
| Domain-level independence, simple tier × confidence × recency | Learned weights, per-topic thresholds |
| Template explanation with top-3 citations | Ack-and-edit delivery (Q1), feedback buttons |
| Offline e2e test (FakeRunner) + structured logs | Eval suite, metrics, quotas UI, feedback |

## 4. Decisions this slice must make (write them down as they happen)

1. **Q3 — search provider**: pick one (cost envelope, Persian support,
   key). Half a day; blocks tasks 11–12.
2. **Q2 — query generation**: heuristics-first (this slice's choice); the
   port keeps the model option open.
3. **Q6 — serving**: in-process runner (recommended, no container until a
   trigger fires).
4. **Delivery**: inline answer or follow-up message per whatever the Q1
   prototype shows; the pipeline is identical either way
   (`03-investigation-lifecycle.md` §1).

## 5. Tasks

Ordered; each is one engineer, one session. `[devops]` / `[mlops]` mark
suitability for those contributors. Checkpoints after tasks 5, 10, and 15.

### Tasks 1–5 — foundation & plumbing

#### Task 1: Scaffold the project `[devops]`

**Description:** uv project, `src/shayeban/` package with empty module
packages matching `01-architecture.md` §2, `pyproject` with ruff,
`mypy --strict`, pytest.

**Acceptance criteria:**
- [ ] `uv sync && uv run ruff check . && uv run mypy && uv run pytest` all pass on an empty test
- [ ] Module directories exist for the ten modules (empty `__init__` is fine)

**Verification:** the four commands above, locally and in CI (task 15 will
wire CI; until then local is enough).
**Dependencies:** none · **Size:** S

#### Task 2: Settings and `.env.example` `[devops]`

**Description:** `pydantic-settings` config object; missing required keys
fail startup with a readable error; `.env.example` documents `BOT_TOKEN`,
`SEARCH_API_KEY`, `DATABASE_URL`.

**Acceptance criteria:**
- [ ] App refuses to start without required settings (test with a clean env)
- [ ] `.env.example` lists every key the code reads

**Verification:** unit test with empty env expects a clear failure.
**Dependencies:** 1 · **Size:** S

#### Task 3: Compose stack with health `[devops]`

**Description:** `docker-compose.yml`: `postgres` (named volume) + `app`
built from the repo Dockerfile, non-root user, healthcheck wired to
`GET /health` (FastAPI app minimal: health route only).

**Acceptance criteria:**
- [ ] `docker compose up` from a clean clone; `curl localhost:8080/health` → 200
- [ ] No published Postgres port (internal network only, `security.md` §5)

**Verification:** manual run + curl; `docker compose ps` shows healthy.
**Dependencies:** 1, 2 · **Size:** M

#### Task 4: Alembic with `investigations` table

**Description:** Alembic initialized against Compose Postgres; first
migration creates `investigations` (id, state, claim_text, language, source
surface, attempts, budget fields, timestamps, error) per
`07-database-schema.md` §4 (minimal column set).

**Acceptance criteria:**
- [ ] Entrypoint runs `alembic upgrade head` before app start
- [ ] Re-running from empty DB is idempotent

**Verification:** `docker compose down -v && docker compose up` → row table
exists.
**Dependencies:** 3 · **Size:** S

#### Task 5: Shared entrypoint: inline query → placeholder verdict

**Description:** aiogram inline query handler builds `RawMessage` and calls
`handle_claim()`; the stub replies "investigating…" (then edits/sends a
placeholder verdict when the stub returns). Group `/factcheck` command calls
the **same** function. No fact-check logic in handlers
(`01-architecture.md` §3).

**Acceptance criteria:**
- [ ] Integration test: synthetic inline update and synthetic group command both reach one `handle_claim()` (assert single path, handler logic untouched)
- [ ] Handlers contain no branching on surface beyond building `RawMessage`

**Verification:** the integration test + one manual inline query on a real
bot (staging token).
**Dependencies:** 2, 3 · **Size:** M — **CHECKPOINT 1: plumbing works**

### Checkpoint 1 — plumbing works (after task 5)

- [ ] Synthetic inline + group updates reach one `handle_claim()` (test)
- [ ] `docker compose up` healthy, migrations applied
- [ ] Placeholder reply visible in a real Telegram chat

### Tasks 6–10 — pipeline skeleton & reasoning

#### Task 6: FSM core

**Description:** state enum (design minus `CLUSTERING`), transition table,
`transition()` raising on illegal moves; stage modules return results, never
transitions (`04-fsm.md` §3).

**Acceptance criteria:**
- [ ] Every legal transition from `04-fsm.md` (minus `CLUSTERING`) is table-driven
- [ ] Tests: illegal transition raises; terminal states are final

**Verification:** `uv run pytest tests/test_fsm.py`.
**Dependencies:** 4 · **Size:** M

#### Task 7: Orchestrator

**Description:** `investigation/` runs stages sequentially in an asyncio
task; each transition persisted transactionally with the stage result;
structured log per transition (`state_from → state_to`, `investigation_id`,
duration).

**Acceptance criteria:**
- [ ] A claim with stub stages reaches `COMPLETED` with all rows written
- [ ] Log lines match the fields in `observability.md` §1

**Verification:** integration test (in-memory fakes) + `jq` on captured logs.
**Dependencies:** 5, 6 · **Size:** M

#### Task 8: Restart policy

**Description:** on startup, non-terminal investigations older than a
threshold → `FAILED (interrupted by restart)` (`04-fsm.md` §5).

**Acceptance criteria:**
- [ ] Test: seeded `HARNESS_RUNNING` row becomes `FAILED` after startup sweep
- [ ] Sweep never touches terminal rows

**Verification:** unit test.
**Dependencies:** 7 · **Size:** S

#### Task 9: `decision/` port + FakeRunner `[mlops]`

**Description:** `PredictRunner` Protocol (detection / stance / verdict
methods) with a deterministic `FakeRunner` ported from `laya-lab`; tests use
it exclusively.

**Acceptance criteria:**
- [ ] FakeRunner returns fixed, configurable results
- [ ] No test depends on real model weights

**Verification:** unit tests green offline.
**Dependencies:** 6 · **Size:** S

#### Task 10: In-process Laya runner `[mlops]`

**Description:** real `PredictRunner` wrapping the pinned checkpoint
(config: which checkpoint, fail-fast when weights missing); wired at
`CLASSIFYING` (detection), `LAYA_ANALYSIS` (stance), `VERDICT` (verdict,
schema-constrained); record `laya_version`, `laya_checkpoint`,
`question_schema_version` on the investigation row.

**Acceptance criteria:**
- [ ] One real local run produces a verdict end to end (manual, recorded in PR)
- [ ] Investigation row carries the three version fields (`mlops.md` §3.1)
- [ ] Missing weights → startup error naming the checkpoint

**Verification:** manual run + DB query; unit test for version recording with
FakeRunner.
**Dependencies:** 9, 7 · **Size:** M — **CHECKPOINT 2: reasoning works**

### Checkpoint 2 — reasoning works (after task 10)

- [ ] Offline e2e with `FakeRunner` reaches `COMPLETED`
- [ ] One real local run produced a verdict; version fields present on the row

### Tasks 11–15 — evidence, verdict, delivery

#### Task 11: Query generation + search provider

**Description:** `QueryGenerator` port with heuristic implementation
(claim keywords → 2 Persian + 2 English queries); `SearchProvider` port with
the Q3 provider implementation (httpx); budget counters start here.

**Acceptance criteria:**
- [ ] Claim → ≤4 queries (fa+en) → ≤5 results each, counted against the budget
- [ ] Provider fully behind the port (swap in tests with a fake)

**Verification:** unit tests with fake provider; one `@live` manual search.
**Dependencies:** Q3 decision, 7 · **Size:** M

#### Task 12: Fetch → extract → evidence items

**Description:** httpx fetch (timeouts, byte caps, content-type checks);
Trafilatura extract with BeautifulSoup fallback; strip scripts at the B1
choke point; emit `EvidenceItem` (url, domain, fetch time, text) with tier
looked up from seeded `sources` rows; URL-normalization + content-hash
dedup.

**Acceptance criteria:**
- [ ] Fixture HTML (including a `<script>` payload) yields clean text
- [ ] ≥3 evidence items for a normal claim, within budget; duplicate URLs collapse

**Verification:** fixture-based unit tests (offline) + one live smoke.
**Dependencies:** 11 · **Size:** M

#### Task 13: Weighting v0 + validation guard

**Description:** tier × confidence × recency roll-up with a domain-level
independence cap → `VerdictCandidate`; validation rules (sufficiency,
independence, budget) → allowed verdict set or `NEEDS_REVIEW`; thresholds in
`config/weights.toml`.

**Acceptance criteria:**
- [ ] Three table-driven scenarios pass: corroborating sources → confirmed class; one source × copies → NOT confirmed; thin evidence → UNCLEAR/NEEDS_REVIEW
- [ ] `weighting/` and `validation/` are pure functions (no I/O) — tested without mocks

**Verification:** `uv run pytest tests/test_weighting.py`.
**Dependencies:** 12, 10 · **Size:** M

#### Task 14: Explanation + delivery

**Description:** render the verdict template with top-3 evidence
(citations: title/domain/URL) and deliver through `bot_gateway` (inline
answer or message per Q1 prototype).

**Acceptance criteria:**
- [ ] Verdict message contains verdict class + ≥1 citation that resolves
- [ ] Pipeline emits `Explanation`; handlers only format it (`03-…` §6)

**Verification:** e2e test asserts message content; manual demo.
**Dependencies:** 13, 5 · **Size:** S

#### Task 15: CI gate + demo runbook `[devops]`

**Description:** `ci.yml`: `docs` (link check), `lint`, `type`, `test` jobs
including the FakeRunner e2e; write the demo runbook (token setup, how to
run, expected output) into the root README quick start.

**Acceptance criteria:**
- [ ] PR with an intentional lint error is red; fixed PR is green
- [ ] e2e job runs with no network credentials (FakeRunner only)

**Verification:** two test PRs (red/green).
**Dependencies:** 1–14 · **Size:** M — **CHECKPOINT 3 / M0 DONE**

## 6. Definition of Done (M0)

- **Demo:** clean clone → `docker compose up` → inline query → verdict
  message with citations, using the real checkpoint, in seconds not hours.
- **CI green:** lint, types, tests, offline e2e — all without secrets.
- **Honest failure:** `kill -9` during an investigation → restart marks it
  `FAILED`; no orphan states.
- **Auditable:** the investigation row shows model + schema versions;
  transition logs reconstruct the run.
- **Docs:** gap-analysis rows updated (implementation vs. design), decisions
  from §4 recorded.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Q3 provider key delayed | `FakeSearchProvider` behind the port keeps tasks 11–14 unblocked (same pattern as FakeRunner) |
| Laya checkpoint heavy to download | develop against FakeRunner; real checkpoint only needed for task 10's manual run |
| Telegram inline timing limits | placeholder-ack first (already the slice's shape); edit-later is Q1, outside the slice |
| Scope creep toward clustering/cache | scope table (§3) is the contract — additions go to the phase backlog in `roadmap.md` |
