# MLOps

> Part of the Shayeban architecture docs. The lightweight model lifecycle:
> how we version, record, evaluate, and change everything that influences a
> verdict — without a registry server, tracking platform, or paid
> infrastructure. This is a primary learning goal of the project; the design
> is deliberately small but complete.

## 1. The two questions the system must answer

1. **"Which model/prompt/configuration produced this investigation?"**
   → answered from data recorded *with every investigation* (§3).
2. **"Did changing the model improve the system?"**
   → answered by comparable **evaluation runs** over a versioned dataset (§4,
   `evaluation.md`).

Everything below exists to make those two answers boringly easy.

## 2. What counts as an artifact (the inventory)

| # | Artifact | Examples | Where it lives |
|---|---|---|---|
| 1 | **Model versions** | `laya` package 0.3.20; checkpoint `multilingual` + HF revision | lockfile + config; recorded per investigation |
| 2 | **Prompts** | question schemas (`QuestionModel` subclasses) — field text, options, levels | source code, versioned in git like any code |
| 3 | **Embedding models** | model producing `claim_clusters.embedding` | config + recorded where embeddings are written (§3.3) |
| 4 | **Inference configuration** | checkpoint routing, device, thresholds/bands (`weighting` config), budgets | versioned config file; content hash recorded |
| 5 | **Evaluation datasets** | golden claims + expected labels | in-repo, git-versioned (`evaluation.md` §3) |
| 6 | **Evaluation runs** | metrics JSON + dataset version + code ref | CI artifacts + optional committed summary |
| 7 | **Model/runtime changes** | PR that moves any row above | normal PR review (the change log *is* git) |

Note what is *not* in the inventory: trained weights of our own — Laya
checkpoints come from the Hugging Face hub, revision-pinned. We consume
models; we don't train them (yet). That alone removes the need for a model
registry.

## 3. Versioning & recording (registry-less, on purpose)

### 3.1 Per-investigation provenance

`investigations` carries the runtime identity of every run
(`07-database-schema.md` §4):

| Column | Answers |
|---|---|
| `laya_version` | which package produced the passes |
| `laya_checkpoint` | which weights (`english`/`multilingual`/…) |
| `question_schema_version` | which prompt definitions (git ref/sha of the schema module) |
| `config_version` *(proposed, §3.4)* | which threshold/weight/band configuration |

Evidence rows additionally pin per-item `laya_confidence` — the recorded
numbers are the source of truth; re-running the model later may not be
bit-identical (GPU/batch nondeterminism), and that is explicitly accepted
(`06-laya.md` §5).

### 3.2 Layered versioning model

```
git commit ──► lockfile (laya==0.3.20, deps) ──► container image tag
    │
    ├── question schemas (prompts) = code = reviewed in the same commit
    ├── config file ──► config_version = hash of effective config
    └── eval/golden/ dataset ──► dataset_version (git sha of the folder)
```

One `git rev-parse HEAD` plus the recorded row tells you the whole story;
the image tag makes the runtime reproducible.

### 3.3 Embedding models — the sneaky one

Cluster embeddings only mean something relative to **the model that produced
them**. Mixing models inside one vector index silently corrupts similarity.

- Pin the embedding model (id + revision) in config like any other model.
- Record the model on write (cluster rows / a `system_config` note) so a
  mismatch is detectable.
- **Changing the embedding model = data migration**: re-embed every cluster
  in one Alembic data migration (`deployment.md` §7), never by mixing old and
  new vectors. This is the clearest example of why model changes are
  *changes with a procedure*, not config edits.

### 3.4 Inference configuration & thresholds

Weights, bands, budgets, and breaking thresholds are **data** (config file),
not code constants (`08-evidence-and-source-weighting.md` §3). The config's
content hash becomes `config_version`, stored per investigation — so "the
verdict used old thresholds" is a query, not an archaeology project.

## 4. Evaluation runs (the "did it improve?" machinery)

Full design in `evaluation.md`; the MLOps contract is:

- A run = **code ref + dataset version + config version + model pins +
  metrics JSON** — all recorded in the run report.
- Reports are CI artifacts (retained by GitHub); runs worth remembering are
  summarized in a committed `eval/RESULTS.md` table (one row per notable
  run) — a "registry" you can read with `git log`.
- Before/after comparison for any change = run the eval on both sides of the
  PR and diff the reports. That is the whole release gate for model/prompt
  changes.

## 5. Change-management workflow (model / prompt / config)

| Step | Action |
|---|---|
| 1 | Branch like any change (`chore/migrate-…`, `feat/…`) |
| 2 | Run the eval locally against the golden set (`uv run python -m eval.run`) |
| 3 | PR includes before/after eval numbers + reason for the change |
| 4 | Review treats prompt text and thresholds as **production logic** — reviewed, not edited casually |
| 5 | Merge; migrations (if the change touches data, e.g. embeddings) run via Alembic |
| 6 | The eval summary row is committed; investigation provenance columns pick up the new versions automatically |

## 6. Reproducibility stance (what "reproduce" means here)

| Level | Guarantee | Status |
|---|---|---|
| Environment | same lockfile + image tag → same code & deps | designed (§3.2) |
| Inputs | evidence rows + original message text persisted | designed (schema) |
| Decision inputs | stance/confidences recorded per evidence item | designed (schema) |
| Model output replay | re-running the model may differ slightly (nondeterminism) | **accepted** — recorded outputs are authoritative |
| Bit-exact full replay | same GPU, same kernels, same batch order | **out of scope** — would require containerized GPU capture; no MVP use case |

## 7. What we deliberately do not build (and the trigger)

| Deferred | Looks like | Trigger |
|---|---|---|
| Model registry server (MLflow etc.) | tracked runs, model store, UI | model artifacts we *own* (fine-tunes, quantized variants) stop fitting comfortably in git/HF |
| Feature/prediction store | centralized online features | multiple consumers of the same features beyond this app |
| Training pipelines | fine-tuning Laya or train-to-order heads | the eval says off-the-shelf checkpoints are the bottleneck |
| Auto-retraining | scheduled jobs acting on metrics | there is anything to retrain |
| Central experiment tracking (W&B…) | dashboards across runs | eval history outgrows a markdown table |

## 8. Repo layout (planned)

```
eval/
├── golden/              # dataset files, versioned in git
│   └── *.jsonl          # claim, expected detection, expected verdict, notes
├── run.py               # runner: pipeline → metrics JSON
└── RESULTS.md           # one row per notable run (code ref, versions, metrics)
config/
└── weights.toml         # thresholds/bands/budgets → hashed as config_version
```

---

<sub>**13/21** · [← Deployment](deployment.md) · [Docs index](README.md) · [Evaluation →](evaluation.md)</sub>
