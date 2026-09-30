# Observability

> Part of the Shayeban architecture docs. What we measure from day one and
> why: every "should this become a service / queue / cluster?" decision later
> must be evidence-based, same as the product itself. (Absorbs §5 of the
> former `03-microservices-architecture.md`.)

## 1. MVP: structured logs, not a monitoring stack

No Prometheus/Grafana/Graylog in the MVP — laptops, portfolio demo, one
operator. What we do from the first working pipeline is **structured JSON
logs to stdout** (docker captures them), greppable with `jq`, because these
fields are exactly what later decisions need:

| Field group | Examples | Decides later |
|---|---|---|
| Correlation | `investigation_id`, `cluster_id`, `attempt`, `state_from` → `state_to` | tracing one run end to end |
| Cost | search API calls, fetches, bytes, per-investigation budget remaining | budget/quota tuning, provider choice |
| Cache | dedup hit/miss, TTL applied, `breaking_mode` at lookup | cache effectiveness, TTL policy |
| Stage timings | duration of classification, clustering, search, fetch, Laya passes, aggregation, explanation | queue-vs-async, Laya service split (`01-architecture.md` §4.2), bottleneck hunts |
| Laya | checkpoint used, question-schema version, latency, error/retry | model swaps, `06-laya.md` versioning |
| Outcomes | terminal state (`COMPLETED` / `REJECTED` / `NEEDS_REVIEW` / `FAILED`), verdict, strength | quality tracking, failure-mode analysis |
| Transitions | every FSM transition with timestamp | lifecycle debugging (the transition history lives here — `04-fsm.md`) |

Two distinctions the fields must keep sharp:

- **`UNCLEAR` (an answer) ≠ `FAILED` (our breakage)** — a rising `FAILED`
  rate is an operational alert; a rising `UNCLEAR` rate may just be the world.
- **`RETRYING` bursts** by stage reveal which dependency is flaky (search vs.
  fetch vs. model).

## 2. Investigation inspection — "what happened to #123?"

Design target: given one `investigation_id`, answer **from the logs alone**:

| Question | Answered by |
|---|---|
| Where was time spent? | per-stage `duration_ms` events |
| Which searches were performed? | search events: query, language, provider, result count |
| Which sources were retrieved? | fetch events: URL, domain, tier, status, bytes |
| Which evidence reached Laya? | `evidence_selected` event: item ids + snippets sent to the stance pass |
| Which model/version ran? | Laya events: checkpoint, package version, question-schema version |
| How was the verdict produced? | aggregation event: per-stance weights, independent groups, thresholds applied, candidate → validated verdict |
| Where did it fail? | terminal state + last error event with stage and retry count |

MVP mechanism: one JSON line per event, all carrying `investigation_id`:

```bash
# every event for one investigation, in order
docker compose logs -f app | jq --arg id 123 'select(.investigation_id == $id)'
```

When `jq` stops being pleasant (repeated debugging, demos to the team), the
same events feed a tiny read-only helper — `shayeban inspect <id>` printing a
timeline. That is a convenience script over the same log stream, **not** a
new storage system; a database-backed trace UI is explicitly a future item
(`future-evolution.md`).

## 3. Signal catalog

The signals worth having, where each comes from, and what it is for:

| Signal | Source | Use |
|---|---|---|
| Investigation latency (total + per stage) | stage timing events | find bottlenecks; decide queue vs. async |
| Search latency | harness search events | provider choice, budget tuning |
| Fetch failures | harness fetch events (status/timeout) | site flakiness, retry policy |
| Model latency | Laya wrapper events | in-process vs. service split decision |
| Model errors | Laya wrapper events | retry logic, checkpoint health |
| Database latency | repository timing (slow-query threshold, e.g. >100ms) | schema/index issues |
| Evidence count per investigation | `evidence_ready` event | harness yield quality |
| Source diversity | unique domains in the evidence set | independence health — low diversity + high count = copy machine |
| Cache/dedup behavior | cluster lookup events (hit/miss, TTL) | dedup effectiveness, TTL policy |
| FSM state transitions | transition events | lifecycle debugging, stuck-investigation detection |

All of these are **derived from the same structured logs** — no second
instrumentation system. If a signal proves unused for a few months, delete
it; if a question can't be answered, add a field. The list is a hypothesis,
not a contract.

## 4. Health

`api/` exposes `GET /health` (process up) and a deeper check (DB reachable;
Laya reachable when split). Compose uses it for container healthchecks.

## 5. Growth path (explicitly later)

1. **Now**: JSON logs + `jq` one-liners during demos and debugging.
2. **When numbers matter**: a tiny log → counters exporter or a metrics
   endpoint (request/latency/state counters), scraped by Prometheus — the
   log fields above map 1:1 to metric labels, so nothing is redesigned.
3. **Only if the system outgrows one box**: centralized logs (Graylog/Loki)
   and dashboards. Not before.

What we will **not** do in the MVP: distributed tracing, APM tooling,
high-cardinality metric stores. One process has one log stream; correlate on
`investigation_id`.

---

<sub>**15/21** · [← Evaluation](evaluation.md) · [Docs index](README.md) · [Security →](security.md)</sub>
