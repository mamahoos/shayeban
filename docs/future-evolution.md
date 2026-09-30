# Future Evolution

> Part of the Shayeban architecture docs. How the system grows
> **intentionally** instead of accumulating infrastructure: for every major
> subsystem — what the MVP does now, what it could become, and the problem
> that would justify the jump. Plus extension points and the team's open
> questions.

## 1. Per-subsystem: MVP → Future → Trigger

| Component | MVP now (why this is enough) | Future | Trigger to evolve |
|---|---|---|---|
| **Docker Compose** | `app` + `postgres` on a laptop; one command, same stack for everyone | multi-host, orchestrator | compose can't express what we need (health-dependent rolling updates across hosts) |
| **Single-process app (asyncio)** | one event loop runs bot + pipeline concurrently; no delivery semantics to get wrong | background workers + queue | measured event-loop saturation: investigations queueing, p95 latency degrading under demo load |
| **Redis / shared cache** | verdict cache lives in Postgres (it's just rows + indexes); cross-process cache has no consumers | Redis for hot cache/pub-sub | a second process exists *and* cache hit latency from Postgres shows up in stage timings |
| **Kubernetes** | nobody operates it; `compose up` is the deployment | any orchestrator | multiple machines or deployment cadence where manual compose deploys actually hurt |
| **Reverse proxy (Traefik) / TLS** | nothing listens on the network; debug ports bind `127.0.0.1` | proxy + TLS in front of the app | a demo must be reachable beyond the laptop/home LAN |
| **`laya-service` container** | in-process runner behind `PredictRunner`; zero network code (`01-architecture.md` §4.2) | separate warm container via `laya.serve` | weight-loading blocks restarts or GPU contention visible in stage timings |
| **Model registry (MLflow-style)** | models are HF checkpoints pinned by revision; provenance in `investigations` rows; eval history in git (`mlops.md`) | registry for owned artifacts | we produce artifacts git/HF can't comfortably hold (fine-tunes, quantized variants) |
| **Prometheus + Grafana** | structured JSON logs + `jq`; signal catalog defined (`observability.md` §3) | metrics endpoint + dashboards | `jq` stops answering "is FAILED rate rising?" fast enough to matter |
| **Centralized logging (Loki/Graylog)** | one container, one log stream | aggregated logs across processes | the system splits into enough processes that `docker compose logs` loses the thread |
| **Distributed tracing** | `investigation_id` correlates every event in one stream | OpenTelemetry spans | services multiply to the point where one log stream can't reconstruct a request |
| **Harness sandboxing** | sanitization + caps in-process (single choke point, `security.md` §2) | fetch/extract in an isolated worker | hostile-content volume or severity outgrows in-process sanitization |
| **Background queue (durable)** | asyncio task per investigation + persisted FSM state; restarts mark orphans `FAILED` (`04-fsm.md` §5) | broker + workers, resume-from-checkpoint | investigations must survive restarts as *work*, not as `FAILED` rows — i.e. real usage appears |
| **Search provider** | one provider behind the harness port, budget-capped (`05-…` §6) | multi-provider failover/federation | provider outages/quotas visibly starve evidence yield |
| **Embedding model change** | one pinned model, recorded, single vector space (`mlops.md` §3.3) | newer/better embeddings | eval shows clustering quality is the bottleneck — shipped as an Alembic re-embed migration, never mixed vectors |
| **Source reputation** | deterministic: tiers + hand-tuned thresholds, auditable (`08-…`) | feedback-driven scoring, learned weights | feedback volume exists and static weights measurably misrank sources |
| **Generative model (extraction/query-gen)** | open question Q2 — heuristics or light model behind a port (`claim_extraction/`) | local LLM / API choice revisited | quality ceiling proven by eval (retrieval recall poor because queries are weak) |
| **Public API / web UI** | `api/` exists with `/health` only | real endpoints + auth | an actual consumer beyond the bot |
| **State-transition history table** | transitions in structured logs (`observability.md` §2) | dedicated table if queried often | debugging/analysis repeatedly needs SQL over the transition history |
| **Inline delivery pattern** | synchronous attempt; async edit unconfirmed (Q1) | ack + edit-later | Telegram constraints confirmed by prototype |
| **FSM resume-from-checkpoint** | restart marks orphans `FAILED` (`04-fsm.md` §5) | resume from `CLAIM_EXTRACTED`/`EVIDENCE_READY` | restarts during active use start losing meaningful work |
| **Feedback loop automation** | `feedback` review queue, manual review | offline job updating weights/tiers | reviewed cases accumulate enough to act on |

Rule of thumb behind every row: **we adopt the upgrade when the current
mechanism's failure is measured, not when the upgrade sounds professional.**
Signals come from `observability.md`; each upgrade must name the signal that
justified it.

## 2. Extension points (one-line index)

Detailed in `01-architecture.md` §5; the non-obvious ones:

- **New verdict classes / question wording**: edit `QuestionModel` subclasses
  + explanation templates; schema version moves with them.
- **New source tiers**: rows in `sources` + weight config — no deploy of
  logic.
- **Second model alongside Laya** (e.g. a generative model answering
  "what does this evidence say in Persian?"): new port beside `decision/`;
  weighting/aggregation untouched as long as outputs map to stance/confidence
  or a new explicitly-typed field.
- **Multi-language explanation**: `explanation/` templates are already
  keyed artifacts; no pipeline change.

## 3. Open questions for the team

| # | Question | Blocks |
|---|---|---|
| Q1 | Inline delivery: can we ack immediately and edit the posted message later (needs `inline_message_id` / callback pattern), or must everything fit Telegram's inline timeout? | `bot_gateway` delivery design |
| Q2 | Which generative model for canonical claim + bilingual query generation — local small LLM, external API, or heuristics-first? | `claim_extraction/`, harness inputs, eval scope |
| Q3 | Which search API (provider, key, cost envelope)? | harness implementation, budgets |
| Q4 | Group scope: privacy mode on (commands only) or off (all messages)? Laya-per-message cost acceptable? | group gate design, quotas |
| Q5 | Confirm FSM ordering choice (`VALIDATION` before `VERDICT`) — see `04-fsm.md` §4 | FSM implementation |
| Q6 | Laya serving: start in-process (recommended) or `laya-service` container from day one, given `laya.serve` exists? | compose topology |
| Q7 | Eval set: who owns the golden claims, and do we gate CI on it or run it manually? | `evaluation.md` |
| Q8 | `weighting/` as its own module vs. living inside `decision/` — confirm the boundary change vs. the former module list | module scaffold |

---

<sub>**17/21** · [← Security](security.md) · [Docs index](README.md) · [Roadmap →](roadmap.md)</sub>
