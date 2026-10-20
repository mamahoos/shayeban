# Research: `PredictRunner` + `FakeRunner` survey (laya-lab)

Issue: #18 — research-first, no production code in this PR.

## Source files surveyed

- `laya_typed.py`
- `test_laya_typed.py`
- `main.py`
- `compare_people.py`

> Line numbers below are from `grep -n` against `laya-lab` at commit
> `5be0d00b31cfb7ce22368ef381521deeb9d6f191`.

## Findings

### 1. `PredictRunner` — methods and signatures

`PredictRunner` is a `Protocol`, not a concrete base class
(`laya_typed.py:70`, `class PredictRunner(Protocol):`). It defines exactly
one method, `decide()` (`laya_typed.py:73`):

```python
def decide(
    self,
    state: StatePayload,
    schema: Any = None,
    *,
    questions: dict[str, Any] | None = None,
    return_details: bool = False,
    **predict_kwargs: Any,
) -> Any: ...
```

- `state` is positional and required, typed as
  `StatePayload = str | dict[str, Any] | list[Any]` (`laya_typed.py:34`;
  the broader `State` alias that also admits `BaseModel` is at
  `laya_typed.py:33`). Pydantic `BaseModel` state is converted to a payload
  before this call via `_as_payload()` (`laya_typed.py:149`).
- `schema` is a second positional parameter but is never passed by `LayaAsker.ask()`
  — only `questions` is used in practice.
- `return_details` is keyword-only, defaults to `False`, and is unused by
  `LayaAsker`.
- `**predict_kwargs` lets a caller forward extra args straight through to the
  real runner (`Router`) without `PredictRunner`/`LayaAsker` needing to know
  about them.
- Because it's a `Protocol`, conformance is structural: `Router` does not need
  to subclass `PredictRunner` explicitly, it only needs a matching `decide()`.

### 2. `FakeRunner` — what it returns, how configurable it is

Defined in `test_laya_typed.py:97` (`class FakeRunner:`), with `decide()`
at `test_laya_typed.py:104`:

```python
class FakeRunner:
    def __init__(self) -> None:
        self.seen_state: StatePayload | None = None
        self.seen_questions: dict[str, Any] | None = None

    def decide(
        self,
        state,
        schema=None,
        *,
        questions=None,
        return_details=False,
        **predict_kwargs,
    ):
        self.seen_state = state
        self.seen_questions = questions
        return {
            "verdict": {"type": "choice", "choice": "cat", "confidence": 0.9},
            "drama": {
                "type": "score",
                "probabilities": {"0": 0.0, "1": 0.05, "2": 0.1, "3": 0.25, "4": 0.6},
            },
            "forgive": {"type": "noul", "noul": 0.8},
        }
```

- The response is **hard-coded**, not a function of `state` or `questions` —
  it is a canned response, not a parametrized stub.
- Its only configurability is as a spy: it records `seen_state` and
  `seen_questions` so tests can assert what it was called with (see
  `test_ask_dumps_a_typed_state_before_running`,
  `test_ask_sends_questions_built_from_the_model`).
- The canned payload exercises all three Laya answer shapes:
  - `choice` → `{"choice": <value>, "confidence": <float>}`
  - `score` → `{"probabilities": {<level>: <float>, ...}}`
  - `noul` → `{"noul": <float>}`
- It loads no weights, no GPU, nothing async — this is exactly why it's safe
  to use in unit tests in place of `Router` (`test_ask_returns_a_validated_model_instance`
  and others).

### 3. Types to mirror in `shayeban/decision/`

From `laya_typed.py`:

| Type                               | Line                                                 | Role                                                                                            |
| ---------------------------------- | ---------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `State` / `StatePayload` (aliases) | `laya_typed.py:33`-`34`                              | Accepted input types before/after serialization                                                 |
| `Options` (frozen dataclass)       | `laya_typed.py:40`                                   | Per-option wording metadata for `choice` fields, attached via `Annotated`                       |
| `Levels` (frozen dataclass)        | `laya_typed.py:50`                                   | Per-level wording metadata for bounded-int `score` fields, attached via `Annotated`             |
| `QuestionModel(BaseModel)`         | `laya_typed.py:59`                                   | Base class for question models; `model_config = ConfigDict(extra="forbid")`                     |
| `PredictRunner` (Protocol)         | `laya_typed.py:70`                                   | Dependency-inversion contract the adapter depends on                                            |
| `QuestionFactory`                  | `laya_typed.py:84` (`build()` at `laya_typed.py:88`) | Builds a Laya question dict from a `QuestionModel` subclass (`build()` classmethod)             |
| `LayaAsker`                        | `laya_typed.py:132` (`ask()` at `laya_typed.py:138`) | Adapter: `ask(state, Model) -> Model instance`                                                  |
| `_as_payload()`                    | `laya_typed.py:149`                                  | Module-level helper: converts `BaseModel` state to a `StatePayload` before `decide()` is called |

Three answer/question kinds must be represented consistently across schema
and runtime: **`choice`** (from `Literal[...]`), **`score`** (from an `int`
bounded by `Field(ge=.., le=..)`), **`noul`** (from `bool`). These three
also define the shape `FakeRunner` returns and must line up with whatever
`answer_to_pydantic()` expects.

### 4. Weights-loading cost / async contract

- None of the surveyed files (`laya_typed.py`, `main.py`, `compare_people.py`,
  `test_laya_typed.py`) contain async code — `decide()` is a plain sync method.
- `main.py` constructs `Router(preload=True, device="cuda")`, implying eager
  weight loading is an option (`preload=True`) and that a GPU device is an
  explicit, user-set dependency — but the loading logic itself lives inside
  the `laya` package, not in any file surveyed here.
- This remains unresolved — see Open Questions below.

## Proposed `shayeban/decision/` module skeleton (types only)

```
shayeban/decision/
├── __init__.py
├── models.py     # QuestionModel, Options, Levels
├── runner.py     # PredictRunner (Protocol) + FakeRunner (test double)
├── factory.py    # QuestionFactory
└── asker.py      # LayaAsker/DecisionAsker adapter
```

No implementation included, per acceptance criteria.

## Open questions

1. What does the `laya` package (not `laya_typed.py`) implement inside `Router`?
   Does it support async in any form?
2. `FakeRunner` is currently defined inline in `test_laya_typed.py` rather than
   a dedicated fakes module — should the port split it into its own file?
3. What exact contract do `answer_to_pydantic()` and `questions_from_pydantic()`
   (from `laya.structured`) impose on the questions/answers dict shape that
   must be reproduced?
4. Should the `choice`/`score`/`noul` type names and answer-shape keys be
   mirrored verbatim, or adapted to `shayeban` naming conventions?

## Recommended next issue

Port `FakeRunner` independently of the real `PredictRunner` — it requires no
GPU/weights and can seed `decision/` tests before the real `Router`-backed
`PredictRunner` port is undertaken.
