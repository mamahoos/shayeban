# DevOps

> Part of the Shayeban architecture docs. The development environment and the
> CI pipeline: one small, maintainable quality gate for a 5-person team.
> Runtime topology and compose live in `deployment.md`; model/eval lifecycle
> in `mlops.md` and `evaluation.md`.

## 1. Principles

- **Reproducibility over convenience**: pinned interpreter, pinned
  dependencies, pinned tools — the same commands on every laptop and in CI.
- **The smallest gate that catches real defects.** Every CI job must justify
  its minutes; jobs that never fail get deleted, not kept for looks.
- **Nothing runs locally that CI doesn't run** — if it passes on my laptop
  and fails in CI, the toolchain drifted.

## 2. Toolchain (design decisions for the scaffold)

| Concern | Choice | Why |
|---|---|---|
| Python | 3.12+ (pin the minor in `.python-version` + CI) | matches async + strict-typing stack |
| Env + lockfile | `uv` (`pyproject.toml` + `uv.lock`) | one tool for venv, lock, and CI install; lockfile = reproducibility |
| Formatter + linter | `ruff format` + `ruff check` | one fast tool, replaces flake8/isort/black sprawl |
| Type checking | `mypy --strict` | project standard; contracts are the architecture (`02-components.md`) |
| Tests | `pytest` (+ `pytest-asyncio` where needed) | default choice; pure-logic tests need no services |
| Dependency audit | `uv audit` / `pip-audit` | known-vulnerability check, seconds, no account needed |
| Pre-commit (optional) | `pre-commit` with the same ruff/mypy hooks | catches gate failures before push; entirely optional for contributors |

Rationale for the set: five jobs cover format, lint, types, tests, and
supply-chain health. Anything beyond this list must first fail regularly on
something real.

## 3. Local workflow (developer experience)

```bash
uv sync                      # exact locked environment
uv run ruff format . && uv run ruff check .
uv run mypy shayeban
uv run pytest                # no Docker required
docker compose up --build    # full stack when integration matters
```

Same commands run in CI — CI calls the make/script targets, not a parallel
copy-pasted version of them (`make lint`, `make typecheck`, `make test`).
One definition of "green".

## 4. CI pipeline (GitHub Actions)

Single workflow `ci.yml`, triggered on `pull_request` and pushes to `main`:

| Job | Command | Catches |
|---|---|---|
| `docs` | internal reference check (every `docs/**` link resolves) + Markdown lint | broken doc links — cheap and runs **today**, before any code exists |
| `lint` | `ruff format --check` + `ruff check` | style drift, dead code, obvious bugs |
| `type` | `mypy --strict` | contract violations between modules |
| `test` | `pytest` (unit; fakes at the edges) | logic regressions — `weighting`, `validation`, FSM transitions, templates |
| `audit` | dependency vulnerability scan | known-CVE dependencies |
| `build` | `docker build` (no push) | Dockerfile rot; guarantees `compose up` stays buildable |

Notes:

- Jobs are independent (parallel) and fast; total budget target < 5 minutes.
- **No deploy job** — deployment is `git pull && docker compose up`
  (`deployment.md` §8). Nothing to deploy to anyway.
- Existing `notify-events.yml` stays untouched (repo-event notifications).
- **Integration tests** (compose smoke: health endpoint, migration applied,
  fake-runner pipeline run) become a `smoke` job once application code lands;
  they are listed here but not built yet — a CI job for a nonexistent app
  would only be green noise.

### Smallest useful gate — what we deliberately skip (for now)

| Skipped | Why now | Trigger to add |
|---|---|---|
| Coverage thresholds | no code to cover; a number before code invites gaming | first real test suite exists — pick a modest floor then |
| E2E/browser tests | no UI; Telegram E2E needs external accounts | public API/web UI appears |
| Container scanning (Trivy etc.) | base images are official, local-only | images are distributed beyond laptops |
| Pre-built self-hosted runners | GitHub-hosted minutes suffice at this size | queue times or GPU runners become a real need |
| Auto-format-on-push bots | noise for a 5-person team | nobody runs the formatter locally (measure first) |

## 5. Secrets in CI

- App/DB secrets never appear in CI — CI does not deploy or run the stack.
- `TELEGRAM_*` secrets are used only by `notify-events.yml`.
- `pull_request` from forks receives **no** secrets by GitHub design; keep
  workflows on `pull_request` (not `pull_request_target`) so that stays true.
- Secret scanning: GitHub secret scanning (free for public repos) + never
  commit `.env`. Optional local `gitleaks` pre-commit hook — cheap, but only
  added if someone actually handles tokens regularly.

## 6. Branch, PR, and review flow

- Branches: `docs/`, `feature/`, `fix/`, `refactor/`, `chore/` + short
  description; keep `main` green and branches short-lived.
- Commits: one logical change, prefix `feat|fix|refactor|test|docs|chore`
  (details in `CONTRIBUTING.md`).
- PRs: link the issue (`Closes #N`), tick the checklist only for verified
  work, one type label, review by at least one other collaborator before
  merge; merge only when checks are green.
- `main` protection / required checks: see issue #2 (branch protection was
  set up there) — this pipeline defines what "required" should mean.

## 7. Growth triggers

| Addition | Trigger |
|---|---|
| Integration/smoke job | application code exists |
| Coverage gate | stable test suite + a floor chosen deliberately |
| Self-hosted runner | GitHub-hosted minutes too slow or too limited |
| Merge queue | merge frequency causes broken-main races (unlikely at 5 people) |
| Release automation/tagging | we start cutting versioned releases |
