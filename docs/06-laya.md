# Laya — Reasoning Integration

> Part of the Shayeban architecture docs. What Laya is, how it is called, and
> what it deliberately does *not* do. Laya's evaluation passes sit at
> **layer 7** of the conceptual map (`00-system-overview.md`); its
> final-verdict pass runs inside layer 10's `VERDICT` step (`04-fsm.md`).
> Laya evaluates — it does not own the fact-checking system.

## 1. What Laya is

Laya (`laya` package, seen at v0.3.20 in `laya-lab`) is a fast,
non-autoregressive **System 1 decision engine with calibrated probabilities**.
You give it a *state* (text/dict) and a set of *questions* with **fixed answer
options**; it returns answers plus calibrated confidences. It is a
decision/classification model — not a text generator.

Three checkpoints ship in one hub repo, selectable through `Router`:

| Checkpoint | Size | Notes |
|---|---|---|
| `english` | 421M, ModernBERT-large, 512 tok | collapses off-English (poor + overconfident) |
| `multilingual` | 322M, mmBERT, 1024 tok, 100+ langs | ~+21 pts over english on non-English XNLI |
| `typed-decisions` | 421M, fine-tuned on typed workflows | opt-in only, never a silent default |

Routing is by script/language detection; **Persian claims must land on the
multilingual checkpoint** — the English one doesn't gently degrade off
English, it collapses while reporting high confidence. Use the router, never
pin `english`.

Why it fits Shayeban: our reasoning steps are all *structured decisions over
fixed option sets* (is this a claim? does this document support or contradict?
which verdict?) with a confidence we can weight mathematically — exactly
Laya's shape, at speed suitable for per-message gating.

## 2. What Laya does for us (three passes)

All three go through the single `decision/` module:

| Pass | FSM state | Question shape (conceptual) |
|---|---|---|
| Claim detection | pre-FSM group gate + `CLASSIFYING` | `is_claim: claim / not_claim / borderline` |
| Per-evidence stance | `LAYA_ANALYSIS` | `stance: support / contradict / irrelevant` (+ calibrated confidence → `evidence.laya_confidence`) |
| Final verdict | `VERDICT` | `verdict: true / false / misleading / unclear / …` + `strength` score with worded levels |

Question schemas are **Pydantic `QuestionModel` subclasses** (the typed
adapter proven in `laya-lab/laya_typed.py`): field type selects question type
(`Literal` → choice, `bool` → noul, bounded `int` → score), `Field(description)`
becomes instructions, `Options()`/`Levels()` give per-option wording. Free-text
fields are rejected by design.

**These question schemas are our prompts.** They are code, reviewed in git,
and versioned per investigation (`mlops.md`).

## 3. What Laya does *not* do

| Not Laya's job | Where it lives instead |
|---|---|
| Searching/fetching the web | `harness/` |
| Weighting sources, independence, aggregation | `weighting/` — Laya outputs stance/confidence only; **repetition never becomes truth through the model** (`08-evidence-and-source-weighting.md`) |
| Writing the user-facing explanation | `explanation/` — Laya emits no free text; verdict prose is templates |
| Generating search queries / canonical claim text | `claim_extraction/` needs a **generative** model — an undecided dependency (`architecture-gap-analysis.md`) |
| Deciding retry/budget/policy | `investigation/` FSM |

This is the point of the layered design: Laya can be replaced (or added to)
without touching retrieval, weighting math, or delivery.

## 4. Serving mode

| Mode | When | How |
|---|---|---|
| **In-process (MVP)** | default | `decision/` constructs the runner behind the `PredictRunner` protocol (`laya-lab/laya_typed.py`); `LayaAsker(runner)` is already transport-agnostic |
| **Separate `laya-service`** | when measured pain appears: restart cost of weight-loading, GPU contention (see `observability.md` stage timings) | upstream `laya.serve` ships an HTTP surface: `POST /v1/systemone`, bearer auth (`LAYA_API_KEY`), `/health`, env-var config (`LAYA_DEVICE`, `LAYA_PRELOAD`, `LAYA_MODELS`, …). Verify the wire protocol against our client before committing — otherwise a thin wrapper we own |

The split is a constructor swap because every call already flows through one
module (`01-architecture.md` §4.2). Requirements for either mode: model
preloaded at startup, health signal exposed, internal-only network if split.

## 5. Versioning & reproducibility

Every investigation records:

| Field | Source |
|---|---|
| `laya` package version | installed distribution |
| checkpoint id (`multilingual`, …) | router selection |
| question-schema version | git ref of the `QuestionModel` definitions |
| calibrations/warnings surfaced at load | `Router` startup log |

Replaying an investigation later means: same evidence rows + same schema
version + same checkpoint. Where exact model weights cannot be reproduced
(e.g. host GPU differences), the recorded confidences on `evidence` remain the
source of truth — investigations are logs, not re-runnable functions.

## 6. Observability hooks

The package exposes hooks (`HookRegistry`, usage aggregation) around
`decide()`; `observability.md` uses them (or wrapper logging) to record
per-pass latency, checkpoint used, and state size. Errors here are retryable
(`RETRYING` in `04-fsm.md`), never silent.
