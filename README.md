# Shayeban

**Shayeban** is a Telegram-based claim/news fact-checking system. A user
submits a claim — by messaging `@shayeban_bot` inline from any chat, or by
sending a message in a group the bot belongs to — and Shayeban investigates
it against the open web, weighs the evidence, and replies with a verdict and
a plain-language explanation.

> **Status: architecture & design phase.** The repository currently contains
> the documentation set and GitHub workflow files — **no application code
> yet**. See [`docs/architecture-gap-analysis.md`](docs/architecture-gap-analysis.md)
> for current-vs-desired.

## Surfaces

| Surface | Behaviour |
|---|---|
| Inline mode | `@shayeban_bot <claim>` works in any chat, no group membership needed |
| Groups | the bot watches messages, uses Laya to judge whether one is a fact-checkable claim, then investigates |

Both surfaces feed **one investigation pipeline**: claim extraction →
clustering → evidence harness → Laya reasoning → weighting/aggregation →
validation → verdict + explanation.

## Quick start

Today (documentation phase):

```bash
git clone git@github.com:mamahoos/shayeban.git
cd shayeban
open docs/README.md        # start with 00-system-overview.md
```

Once the scaffold lands (designed in [`docs/deployment.md`](docs/deployment.md)):

```bash
cp .env.example .env       # add BOT_TOKEN / SEARCH_API_KEY
docker compose up          # postgres + migrations + app
```

## Documentation

The index and reading order live in [`docs/README.md`](docs/README.md).
Start at [`docs/00-system-overview.md`](docs/00-system-overview.md).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for branching, commit, and PR
conventions.

## License

[GNU GPL v3](LICENSE).
