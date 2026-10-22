# Research: Laya question schemas

> Part of the Shayeban architecture docs. Research supplement outside the numbered reading order; proposals require review.

Issue: #21. Research-only proposal, reviewed 2026-10-22; no production schemas or model execution. Timebox: less than half a day.

## Evidence and scope

- [A: pinned laya-lab adapter](https://github.com/mamahoos/laya-lab/blob/5be0d00b31cfb7ce22368ef381521deeb9d6f191/laya_typed.py#L59-L158): question types, factory and answer adapter.
- [B: pinned adapter tests](https://github.com/mamahoos/laya-lab/blob/5be0d00b31cfb7ce22368ef381521deeb9d6f191/test_laya_typed.py#L20-L150): type mappings, marker rejection, fixed answer envelopes and projection.
- [C: example application](https://github.com/mamahoos/laya-lab/blob/5be0d00b31cfb7ce22368ef381521deeb9d6f191/main.py#L17-L40): toy judgment, not a fact-check schema.
- [D: exact locked Laya 0.4.7 wheel source](https://files.pythonhosted.org/packages/3e/6e/4034dff73797ebe6ed7f0ae55bc85d866a6daa4778fdcad25a83827cc353/laya-0.4.7-py3-none-any.whl): `laya/structured.py` lines 181?300 (schema planning/projection), 302?369 (details/decide). Source inspected without installing/importing Laya. Package identity: [PyPI release](https://pypi.org/project/laya/0.4.7/) and repository `uv.lock`, package laya.
- Project intent: `06-laya.md` ?2 (three passes), `07-database-schema.md` ?3?4 (stance/confidence/provenance), `08-evidence-and-source-weighting.md` ?3 (candidate/strength), `mlops.md` ?3.1?3.2 (schema version), `security.md` ?4 (fixed choices/untrusted data).

The repository defines conceptual pass labels; the surveyed lab demonstrates generic toy questions. It does not supply exact Shayeban prompts. The schemas below are explicit M0 proposals, not previously approved definitions. They use TRUE/FALSE/UNCLEAR for the first slice; doc 06's broader misleading/other vocabulary is unresolved and must not be silently invented. Sources: A?C and project intent above.

## Field-level contracts and examples (proposed)

Input state is trusted structured context containing untrusted quoted claim/evidence text, never instructions from that text. Detection receives claim text/language; stance receives one claim and one identified evidence item; verdict receives capped evidence, candidate and validation's allowed labels. These are proposed adapter handoffs following `security.md` ?2/4, `06-laya.md` ?2 and `08-evidence-and-source-weighting.md` ?1/3; they are not new runner parameters.

| Pass | Question field | Fixed values / meaning | Raw fixture answer | Projected answer |
|---|---|---|---|---|
| Detection | is_claim | claim: externally checkable assertion; not_claim: greeting/opinion/request; borderline: insufficient context | `{"is_claim":{"type":"choice","choice":"claim","confidence":0.9}}` | `{"is_claim":"claim"}` |
| Stance | stance | support: evidence affirms claim; contradict: evidence refutes it; irrelevant: neither | `{"stance":{"type":"choice","choice":"support","confidence":0.8}}` | `{"stance":"support"}` |
| Verdict | verdict | TRUE: supported; FALSE: contradicted; UNCLEAR: insufficient/unresolved | `{"verdict":{"type":"choice","choice":"UNCLEAR","confidence":0.7},"strength":{"type":"score","probabilities":{"0":0.8,"1":0.15,"2":0.05}}}` | `{"verdict":"UNCLEAR","strength":0}` |
| Verdict | strength | bounded integer 0..2: weak/moderate/strong; proposal for the model question, not a replacement for pure-core strength | same combined fixture above | map 0?weak, 1?moderate, 2?strong at the adapter |

These fixture values demonstrate shape, not real model accuracy. Field vocabulary follows doc 06 ?2 and doc 08 ?3; raw choice/score shapes and argmax projection follow B:97?131 and D:261?300. Relevance is encoded as irrelevant stance in this proposal; no extra generated prose, free-text explanation, confidence question or NEEDS_REVIEW truth option is added (`security.md` ?4/9; `04-fsm.md` validation outcome).

Confidence is runner metadata, not a question field. Preserve raw field answers before projection: lab `LayaAsker.ask()` returns only the Pydantic values, so stance confidence would otherwise be lost (A:138?147). Proposed adapter result pairs the typed value with validated finite [0,1] confidence and evidence identity; invalid/missing confidence fails explicitly rather than defaulting to perfect confidence. Persist the agreed stance metric as evidence.laya_confidence (doc 07 ?3). Do not treat a score probability vector as a scalar strength confidence.

Important version distinction: Laya 0.4.7 distinguishes legacy `confidence` (choice/score normalized-entropy style certainty) from `answer_confidence` (reported-answer probability, subject to calibration caveats); `DecisionResult` exposes both plus probabilities (D:35?70,302?323). The lab fake's `confidence: 0.9` does not establish calibrated probability semantics. **Escalated to #24/owner:** choose the persisted stance metric against the pinned runtime, record the mapping, and evaluate calibration. The draft transport shape below names legacy confidence explicitly; it does not resolve this statistical policy.

## Draft Pydantic declarations (types only)

This block is standalone Pydantic draft material, not code to import into production. `QuestionModel` mirrors extra-forbid; actual factory integration must also attach reviewed Options/Levels wording. Wording comes from descriptions and the field table above; every wording/option/level/order change is a prompt revision (A:40?67,88?129; `mlops.md` ?2/5).

```python
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class QuestionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DetectionQuestions(QuestionModel):
    is_claim: Literal["claim", "not_claim", "borderline"] = Field(
        description="Classify whether the quoted input asserts an externally checkable fact."
    )


class StanceQuestions(QuestionModel):
    stance: Literal["support", "contradict", "irrelevant"] = Field(
        description="Does this evidence support, contradict, or fail to address the claim?"
    )


class VerdictQuestions(QuestionModel):
    verdict: Literal["TRUE", "FALSE", "UNCLEAR"] = Field(
        description="Select a verdict using only the supplied independent evidence and allowed labels."
    )
    strength: Annotated[int, Field(strict=True, ge=0, le=2)] = Field(
        description="Rate evidential strength: 0 weak, 1 moderate, 2 strong."
    )


class StanceObservation(BaseModel):
    # Adapter output; never pass this free-string/float model to QuestionFactory.
    model_config = ConfigDict(extra="forbid")
    evidence_id: str = Field(min_length=1)
    stance: Literal["support", "contradict", "irrelevant"]
    legacy_confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
```

No Options/Levels classes are copied here: their exact implementations and coverage checks are in A:40?56,103?129. Before implementation, supply complete option descriptions matching each Literal exactly and three level descriptions in ascending order. Numeric metadata/confidence stays outside the question model; the schema subset does not accept arbitrary numeric/free-string outputs (A:59?67; B:60?94; D:181?233).

## How constraints actually work

1. **Before inference:** `questions_from_pydantic()` plans fixed questions; free strings, nested objects and arrays are rejected. The lab factory enforces exact Options coverage and bounded Levels count (A:88?129; B:35?94; D:181?259).
2. **Inference boundary:** the lab calls `runner.decide(payload, questions=...)` synchronously. In locked 0.4.7, structured decide calls `runner.predict` with those questions. This is fixed-choice/score inference, not evidence of an autoregressive JSON grammar (A:138?147; D:327?369). No grammar guarantee is claimed for uninspected internals.
3. **After inference:** choice labels are projected to values; score chooses the highest-probability level (plus minimum); noul uses >=0.5. `answer_to_pydantic()` constructs the model and validates it. Missing required fields or invalid Literal/range values fail validation; low-confidence abstention can project None, which these required fields reject. The existing adapter does not itself enforce a runtime allowed-verdict subset (D:261?300; A:138?147).
4. **Application guard (proposal):** exclude disallowed verdict options before the final pass, recheck the returned label after it, and prevent model strength from upgrading pure-core strength. If only UNCLEAR is allowed, return the deterministic unclear result instead of constructing a one-option question; NEEDS_REVIEW skips the final model call. This is required future wiring, not behavior already present in the generic adapter (`04-fsm.md`; `08-evidence-and-source-weighting.md` ?3; `security.md` ?9). Choose/cache per-allowed-set schema variants only after tests of the locked runtime.

## Proposed question_schema_version

Persist the **full immutable 40-character Git commit SHA of the reviewed schema bundle** in investigations.question_schema_version; resolve a tag/branch to a commit before recording it. The bundle must include models, field descriptions, option/level wording/order, projection and allowed-label/strength mapping. Use the same bundle for every pass in one investigation. Do not store a moving branch name, package version or this research note's SHA as if it identifies implemented schemas. This concretizes `mlops.md` ?3.1?3.2 and `06-laya.md` ?5.

Record package/checkpoint separately, and config_version separately; dynamic allowed labels come from recorded validation inputs/config and must be retained with run results. Build/deployment should inject the source SHA for packaged artifacts without .git and refuse missing provenance for real runs. Dirty local schema runs must not claim the clean SHA: reject them for persisted/evaluation runs, or mark disposable experiments explicitly outside that provenance contract. This is a proposal for #24, not a migration or startup implementation. Wording, enum, ordering, score-level, adapter or mapping edits require a new bundle revision plus fixture/evaluation comparison (`mlops.md` ?4?5).

## Open questions

| Question | Disposition / owner |
|---|---|
| What mechanism constrains answers? | Resolved for inspected adapter/runtime: schema planning plus fixed questions and post-validation, not a demonstrated grammar. |
| Which confidence metric feeds weighting? | Escalate to #24/owner: locked 0.4.7 legacy certainty and answer probability differ; establish and test mapping/calibration before wiring. |
| Exact M0 vocabulary, prompt wording and strength levels? | Proposed above; owner review required. Broader MISLEADING/other classes deferred until separately specified. |
| Allowed-set variants and strength reconciliation? | Escalate to #24: offline cases must prove forbidden labels cannot be delivered and model strength cannot upgrade core strength; review outcome bypasses model. |
| Schema identity persistence? | Full reviewed bundle SHA proposed; #24 implements startup injection and persistence with database owner. |
| Confidence preservation, invalid output and abstention? | #24 adapter must retain metadata and surface typed failure; FSM owner decides review/retry outcome. No silent defaults/coercion into confirmation. |

## Recommended next issue

Use #24 as the implementation follow-up after owner confirms the proposed contracts and #20's runner port is available. First implement the typed factory/adapter offline: all three examples, Options/Levels coverage, bad/missing labels, invalid confidence, abstention, allowed-set enforcement, strength mapping and version identity. Then wire the real pinned runner and provenance; no new duplicate implementation issue is needed. Research acceptance is review of this note, not a claim that inference or the pipeline is implemented.

---

Research supplement · [Previous: runner survey](laya-predictrunner-port.md) · [Docs index](../README.md) · [Next: implementation issue #24](https://github.com/mamahoos/shayeban/issues/24)
