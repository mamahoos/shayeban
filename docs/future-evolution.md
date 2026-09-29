# Future Evolution

> Part of the Shayeban architecture docs. What is deliberately deferred, where
> each deferred capability plugs in, and the evidence-based triggers for the
> structural changes we are *not* making yet.

## 1. Deferred on purpose (and where it lands later)

| Deferred capability | Plugs in at | MVP stand-in |
|---|---|---|
| Dynamic source reputation / learned weights | `weighting/` + `sources` columns, updated by offline job from `feedback` | static tiers + hand-tuned thresholds (data, not code) |
| Feedback-driven tuning loop | `feedback` table → reviewed cases → weight/threshold config | review queue exists; no automation |
| Job queue / background workers | `investigation/` orchestrator (already the single call site) | asyncio tasks in one process |
| Laya as separate service | constructor swap behind `PredictRunner` (`06-laya.md` §4) | in-process runner |
| Resume-from-checkpoint FSM | persisted checkpoints already exist (`CLAIM_EXTRACTED`, `EVIDENCE_READY`) | restart → mark interrupted investigations `FAILED` |
| Public API / web UI | `api/` module + existing repositories | `/health` only |
| Generative model (canonicalization, query-gen) | port inside `claim_extraction/` | *undecided — see gap analysis; biggest open dependency* |
| Inline "ack now, edit later" delivery | `bot_gateway` delivery abstraction | synchronous attempt; product question Q1 below |
| Per-topic breaking thresholds, learned velocity | `harness` volatility config | global fixed thresholds (`05-…` §5.2) |
| State-transition history table | new table (if logs prove insufficient) | structured logs carry transitions (`09-…`) |
| Public exposure (Traefik, TLS, edge rate limits) | compose additions | laptop-only by default (`11-…` §4) |
| Centralized observability stack | log fields map to metric labels (`09-…` §3) | JSON logs + `jq` |

## 2. Split triggers (evidence-based, not aesthetic)

| Change | Trigger (measured) | Cost if done early |
|---|---|---|
| `laya-service` container | weight-loading blocks restarts / GPU contention visible in stage timings | second process to operate for no gain |
| Queue + workers | investigations queuing behind a single event loop; p95 stage latency degrades under demo load | Redis/broker ops, delivery semantics, exactly-once headaches |
| Harness isolation | untrusted-content threat grows beyond sanitization-in-process (larger crawl volumes, hostile sites) | sandbox IPC complexity |
| Postgres off the laptop | multi-user demo needs uptime beyond one machine | backup/DR burden with no users |
| Metrics stack | `jq` stops being enough to answer "is FAILED rate rising?" | running Prometheus/Grafana for one operator |

Each trigger names a signal produced by `09-observability.md` — if we can't
measure it, we don't act on it.

## 3. Extension points (one-line index)

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

## 4. Open questions for the team

| # | Question | Blocks |
|---|---|---|
| Q1 | Inline delivery: can we ack immediately and edit the posted message later (needs `inline_message_id` / callback pattern), or must everything fit Telegram's inline timeout? | `bot_gateway` delivery design |
| Q2 | Which generative model for canonical claim + bilingual query generation — local small LLM, external API, or heuristics-first? | `claim_extraction/`, harness inputs, eval scope |
| Q3 | Which search API (provider, key, cost envelope)? | harness implementation, budgets |
| Q4 | Group scope: privacy mode on (commands only) or off (all messages)? Laya-per-message cost acceptable? | group gate design, quotas |
| Q5 | Confirm FSM ordering choice (`VALIDATION` before `VERDICT`) — see `04-fsm.md` §4 | FSM implementation |
| Q6 | Laya serving: start in-process (recommended) or `laya-service` container from day one, given `laya.serve` exists? | compose topology |
| Q7 | Eval set: who owns the golden claims, and do we gate CI on it or run it manually? | `10-devops-mlops.md` §6 |
| Q8 | `weighting/` as its own module vs. living inside `decision/` — confirm the boundary change vs. the former module list | module scaffold |
