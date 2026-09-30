# MLOps Roadmap

> Part of the Shayeban architecture docs. Which roadmap tasks a
> MLOps-flavored contributor can own: model/runtime boundaries, version
> recording, evaluation infrastructure, and run artifacts — registry-less on
> purpose (`mlops.md`). Not a mandate to do all of it; triggers decide.

## 1. Who this is for

A teammate who wants to own the "model lifecycle" side: keeping runs
reproducible, measured, and swappable — without standing up infrastructure
the project does not need.

## 2. MLOps tasks by phase

| Phase | Tasks (owner tags from `roadmap.md` / `first-milestone.md`) |
|---|---|
| **M0** | T9 `PredictRunner` port + deterministic `FakeRunner` (from `laya-lab`) · T10 in-process Laya runner with pinned checkpoint + fail-fast; record `laya_version` / `laya_checkpoint` / `question_schema_version` on investigations (`mlops.md` §3.1) |
| **Phase 4** | Keep the model boundary clean: checkpoint pinned in config; missing weights fail startup with a readable error |
| **Phase 5** | `config/weights.toml` hashed to `config_version` (`mlops.md` §3.4) so verdicts are reproducible against config |
| **Phase 7** | Seed `eval/golden/` with a `MANIFEST.md` (30–50 hand-verified fa+en items) · `eval/run.py` runner (offline → model mode) · version pins in every run + `eval/RESULTS.md` row (`mlops.md` §8) · verify inference metadata on live investigations · wire the soft CI eval gate with the `[devops]` task |
| **Phase 8** | Reproducibility check: same lockfile + image tag → same env (`mlops.md` §3.2) |

Suggested picking order: **M0 T9 → T10** (unblocks all reasoning work via
FakeRunner), then the eval stack when Phase 7 opens.

## 3. Deliberately not now (and the trigger)

Everything in `mlops.md` §7 — repeated here so this doc is self-contained:

| Skipped | Trigger |
|---|---|
| Model registry server (MLflow etc.) | artifacts we *own* (fine-tunes, quantized variants) stop fitting git/HF |
| Feature/prediction store | multiple consumers of the same features |
| Training / fine-tuning pipelines | eval says off-the-shelf checkpoints are the bottleneck |
| Auto-retraining jobs | there is anything to retrain |
| Central experiment tracking (W&B…) | eval history outgrows the `RESULTS.md` markdown table |
| GPU CI runners | model-mode CI runtime is measured and unacceptable — until then, model evals run locally |
| Prompt-registry service | prompts are code, reviewed in the same commit (`mlops.md` §3.2) |

## 4. Standing rules for this track

- Recorded outputs are authoritative: model re-runs may differ slightly and
  that is accepted — provenance beats bit-exactness (`mlops.md` §6).
- Every eval number in a PR cites its pins (git sha, checkpoint, schema,
  config hash) — a bare number is not reviewable (`evaluation.md` §4).
- The dataset is hand-verified; no LLM-generated gold labels
  (`evaluation.md` §3).
- If a task here seems to require a skipped system, the task is wrong —
  re-read §3 first.
