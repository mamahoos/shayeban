# Evaluation

> Part of the Shayeban architecture docs. A small evaluation framework for
> the AI components: what we measure, on what data, with what runner —
> starting from a handful of curated cases and designed to grow. Ties into
> `mlops.md` §4 (runs are recorded artifacts).

## 1. Why unit tests are not enough

Unit tests prove our code does what we wrote (`weighting` sums correctly,
the FSM transitions legally). They cannot answer **whether the system judges
well**: does detection flag real claims, does Laya assign the right stance,
does the final verdict agree with reality? Fact-checking quality is an
empirical property — it needs a curated dataset and repeated measurement.

Scope discipline: this is **not** a benchmark suite. Small, curated, cheap to
run, run often.

## 2. Evaluation targets

| # | Target | What is measured | Kind of test | Cost |
|---|---|---|---|---|
| 1 | **Claim detection** | accuracy / precision / recall on `claim` vs `not_claim` for messages & inline queries | model (Laya) | low |
| 2 | **Claim extraction** | canonical claim matches a human-written gold claim (semantic similarity + rubric spot-check) | model + heuristic | low |
| 3 | **Evidence retrieval** | recall@k: does top-k search results contain at least one relevant document (or a gold URL)? | external (search API) | $$ + flaky |
| 4 | **Evidence relevance** | precision: of fetched docs, share judged relevant to the claim | model/human labels | medium |
| 5 | **Source weighting** | given synthetic evidence packages (tiers, copies, contradictions), does the roll-up produce the expected verdict? | deterministic scenarios | none — offline |
| 6 | **Laya reasoning** | per-evidence stance accuracy + confidence sanity (avg confidence on correct vs incorrect) | model | low |
| 7 | **Final verdict** | end-to-end verdict agreement on claims with gold verdicts (`TRUE/FALSE/MISLEADING/UNCLEAR…`) | full pipeline | medium |
| 8 | **Explanation quality** | rubric checklist: matches the verdict, cites real evidence, no unsupported claims, correct breaking-mode wording | human-scored | medium |

Targets 1–2–6–7 are the daily drivers; 3–4 need the search API and stay
manual/scheduled; 5 is pure logic (runs in CI from day one of the code);
8 stays human until (if ever) a judge model earns its place.

## 3. Dataset design (start small, grow deliberately)

```
eval/golden/
├── detection.jsonl     # raw message → expected label   (Persian + English)
├── stance.jsonl        # claim + evidence snippet → expected stance
├── verdict.jsonl       # claim → expected verdict class (+ notes on ambiguity)
├── weighting.jsonl     # synthetic evidence package → expected verdict
└── MANIFEST.md         # size, languages, how items were chosen, known gaps
```

Per item (conceptual): `id`, `text`, `lang`, expectations for the relevant
target, optional `notes` (e.g. "many acceptable phrasings"), `category`.

Rules that keep a small dataset honest:

- **30–50 items to start** — every item hand-written or hand-verified; no
  scraped labels, no LLM-generated gold (we'd be grading ourselves).
- **Both languages from item one** — Persian claims are the product's core;
  an English-only eval would miss the multilingual-checkpoint failure modes
  (`06-laya.md` §1).
- **Ambiguity is labeled, not hidden**: items where `UNCLEAR` is a fair
  answer say so — the eval must not punish calibrated caution.
- **Versioned in git** — the dataset version is the folder's git sha
  (`mlops.md` §3.2); every run records it.
- Growth path: add per-target files, split by category, then consider a
  held-out set **once** we notice ourselves tuning to the golden set.

## 4. Runner

One entry point, three execution modes (the runner picks per target):

| Mode | Targets | Needs | Where it runs |
|---|---|---|---|
| **Offline** | weighting scenarios, explanation templates, FSM fixtures | nothing | laptop + CI, seconds |
| **Model** | detection, extraction, stance, verdict | Laya runner (CPU or GPU) | laptop first; CI only after CPU run-time is measured and acceptable |
| **Live** | retrieval, relevance | search API key, budget | manual / scheduled — cost and flakiness make it a poor CI citizen |

Output: `eval/runs/<timestamp>-<gitsha>.json` (metrics + all version pins
from `mlops.md` §3) plus a Markdown summary for the PR description. The
runner reuses pipeline modules with fixed inputs — it evaluates the *system*,
not a parallel reimplementation.

## 5. Execution modes over time

| Phase | When | Gate? |
|---|---|---|
| Now (design) | — | — |
| Manual local runs | whenever reasoning/thresholds/prompts change | reviewer looks at numbers in the PR |
| Offline + model subset in CI | once code exists and CPU time is measured | soft gate (report, don't block) |
| Full suite on schedule (live targets included) | when search spend is budgeted | trend signal, never blocking |

Hard CI gates on metrics come last, if ever — a flaky gate on a 40-item
dataset breeds mute-button culture.

## 6. Anti-goals

- No leaderboard, no dashboard, no tracking server — a JSON report and a
  markdown table are the product.
- No optimizing thresholds against the same set we report (see held-out
  note, §3).
- No LLM-as-judge for explanations in the MVP: humans score eight items in
  five minutes; a judge model would need its own eval first.

---

<sub>**14/21** · [← MLOps](mlops.md) · [Docs index](README.md) · [Observability →](observability.md)</sub>
