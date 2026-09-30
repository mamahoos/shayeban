# Contributing to Shayeban

Team of five; everyone reviews, everyone merges to `main` through a PR.

## Git workflow

- **Branches**: `docs/`, `feature/`, `fix/`, `refactor/`, `chore/` + a short
  description, cut from `main`. Keep `main` green; branches short-lived.
- **Commits**: one logical change per commit, prefixed
  `feat` | `fix` | `refactor` | `test` | `docs` | `chore`. Commit each
  verified slice — never one mixed mega-commit. No secrets, no `.env`, no
  build artifacts.
- Sync with the base branch often; re-verify after resolving conflicts.

## Pull requests

1. Link the issue with `Closes #N` (open an issue first for anything that
   needs review criteria; skip issues for one-file chores).
2. Fill the PR template honestly — tick checklist boxes **only for work you
   actually verified**; unfinished boxes block the merge gate.
3. Exactly one type label (`bug` | `enhancement` | `chore` |
   `documentation`).
4. At least one other collaborator reviews; merge only when checks are green
   and the checklist gate passes.

## Documentation conventions

- Architecture docs are numbered (`00`–`08`); engineering docs use plain
  names (`devops.md`, `deployment.md`, `mlops.md`, `evaluation.md`,
  `observability.md`, `security.md`, `future-evolution.md`); planning docs
  are `roadmap.md`, `first-milestone.md`, `devops-roadmap.md`,
  `mlops-roadmap.md`.
- The index and reading order live in [`docs/README.md`](docs/README.md);
  the layer numbering every doc references comes from
  [`docs/00-system-overview.md`](docs/00-system-overview.md).
- Each doc starts with the `> Part of the Shayeban architecture docs …`
  blockquote; use Mermaid for diagrams; keep cross-references as
  `` `NN-file.md` `` / `` `file.md` `` so link checks can verify them.
- Update `docs/architecture-gap-analysis.md` when a gap closes or a new one
  appears.

## Local development

The application scaffold has not landed yet — until it does, "working
locally" means editing and reviewing docs, and checking that cross-file
references still resolve (a docs link-check job is designed in
[`docs/devops.md`](docs/devops.md) §4 and ships with the scaffold).

After the scaffold (contract defined in [`docs/devops.md`](docs/devops.md)):

```bash
uv sync
uv run ruff format . && uv run ruff check .
uv run mypy shayeban
uv run pytest
docker compose up --build   # full stack
```

`docker compose down -v` **destroys** local data — use it knowingly.

## Security

Never commit `.env`, tokens, or API keys; secrets go in `.env`
(git-ignored) or GitHub Actions secrets. Report suspected exposures to
`mamahoos` immediately — see [`docs/security.md`](docs/security.md).
