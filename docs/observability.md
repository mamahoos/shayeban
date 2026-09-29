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

## 2. Health

`api/` exposes `GET /health` (process up) and a deeper check (DB reachable;
Laya reachable when split). Compose uses it for container healthchecks.

## 3. Growth path (explicitly later)

1. **Now**: JSON logs + `jq` one-liners during demos and debugging.
2. **When numbers matter**: a tiny log → counters exporter or a metrics
   endpoint (request/latency/state counters), scraped by Prometheus — the
   log fields above map 1:1 to metric labels, so nothing is redesigned.
3. **Only if the system outgrows one box**: centralized logs (Graylog/Loki)
   and dashboards. Not before.

What we will **not** do in the MVP: distributed tracing, APM tooling,
high-cardinality metric stores. One process has one log stream; correlate on
`investigation_id`.
