"""Validation guard (spec §8.4): allowed verdict set, or NEEDS_REVIEW.

PURE module (invariant I8): no I/O, no clock, no global state. It runs BEFORE
the final Laya pass; the returned ``allowed_verdicts`` is what that pass is
schema-constrained to, so the output cannot leave the allowed space.

It reuses the floor/threshold functions of :mod:`shayeban.weighting`, so the
roll-up and the guard can never disagree about a bar.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from shayeban.weighting import (
    BudgetConfig,
    BudgetState,
    Config,
    Stance,
    Strength,
    Verdict,
    VerdictCandidate,
    VerdictLabel,
    WeightedEvidence,
    config_hash,
    effective_thresholds,
    floor_failures,
    margin_of,
)

__all__ = [
    "ValidationResult",
    "apply_validation",
    "budget_exhausted",
    "build_verdict",
    "validate",
]


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of the guard (spec §8.4).

    ``allowed_verdicts`` always contains UNCLEAR unless the run needs review,
    in which case it is exactly ``{NEEDS_REVIEW}``. ``evidence_gathering_open``
    tells the orchestrator whether more evidence could still be fetched.
    """

    allowed_verdicts: frozenset[VerdictLabel]
    needs_review: bool
    candidate_permitted: bool
    evidence_gathering_open: bool
    reasons: tuple[str, ...]


def budget_exhausted(budget: BudgetState, limits: BudgetConfig) -> bool:
    """True once the search or per-query fetch budget is used up (spec §8.4)."""
    return (
        budget.searches_used >= limits.max_searches
        or budget.fetches_used >= limits.max_fetches_per_query
    )


def validate(
    weighted: WeightedEvidence,
    candidate: VerdictCandidate,
    cfg: Config,
    budget: BudgetState,
) -> ValidationResult:
    """Compute the allowed verdict set, or NEEDS_REVIEW (spec §8.4).

    Checks, in order: usable evidence, independence floor, tier floor,
    breaking-mode constraints (fresh high-tier + raised bar), and budget state.

    * UNCLEAR is always allowed (I3, I11). TRUE/FALSE are allowed only when that
      side clears every floor AND wins by the required margin.
    * Both sides clearing the floors without a clear winner, or a roll-up that
      already flagged NEEDS_REVIEW, yields NEEDS_REVIEW.
    * Budget exhaustion with insufficient evidence stays on the UNCLEAR path -
      never rejected, never an error (ambiguity #6, I11).
    """
    thresholds = effective_thresholds(cfg, candidate.breaking_mode)
    support = weighted.support_total
    contradict = weighted.contradict_total
    margin = margin_of(support, contradict)
    exhausted = budget_exhausted(budget, cfg.budget)

    support_failures = floor_failures(weighted, Stance.SUPPORT, thresholds)
    contradict_failures = floor_failures(weighted, Stance.CONTRADICT, thresholds)
    support_ok = not support_failures
    contradict_ok = not contradict_failures
    decisive = margin >= thresholds.margin and support != contradict

    reasons: list[str] = []
    if weighted.independent_group_count == 0:
        reasons.append("no_usable_evidence")
    if candidate.breaking_mode:
        reasons.append("breaking_mode_raised_bar")

    conflict = support_ok and contradict_ok and not decisive
    if candidate.verdict is VerdictLabel.NEEDS_REVIEW or conflict:
        reasons.append("contradictory_high_tier_evidence")
        if exhausted:
            reasons.append("budget_exhausted")
        return ValidationResult(
            allowed_verdicts=frozenset({VerdictLabel.NEEDS_REVIEW}),
            needs_review=True,
            candidate_permitted=candidate.verdict is VerdictLabel.NEEDS_REVIEW,
            evidence_gathering_open=not exhausted,
            reasons=tuple(dict.fromkeys(reasons)),
        )

    allowed: set[VerdictLabel] = {VerdictLabel.UNCLEAR}
    if decisive and support > contradict:
        if support_ok:
            allowed.add(VerdictLabel.TRUE)
        else:
            reasons.extend(support_failures)
    if decisive and contradict > support:
        if contradict_ok:
            allowed.add(VerdictLabel.FALSE)
        else:
            reasons.extend(contradict_failures)
    if not decisive and weighted.independent_group_count > 0:
        reasons.append("margin_below_threshold")

    confirmable = VerdictLabel.TRUE in allowed or VerdictLabel.FALSE in allowed
    if not confirmable and exhausted:
        reasons.append("budget_exhausted")
    return ValidationResult(
        allowed_verdicts=frozenset(allowed),
        needs_review=False,
        candidate_permitted=candidate.verdict in allowed,
        evidence_gathering_open=not confirmable and not exhausted,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def apply_validation(
    candidate: VerdictCandidate, result: ValidationResult
) -> VerdictCandidate:
    """Attach the allowed set to the candidate, overriding a verdict outside it.

    An out-of-set verdict falls back to NEEDS_REVIEW (when the guard says so) or
    UNCLEAR, always with WEAK strength.
    """
    if candidate.verdict in result.allowed_verdicts:
        return replace(candidate, allowed_verdicts=result.allowed_verdicts)
    fallback = (
        VerdictLabel.NEEDS_REVIEW if result.needs_review else VerdictLabel.UNCLEAR
    )
    return replace(
        candidate,
        verdict=fallback,
        strength=Strength.WEAK,
        allowed_verdicts=result.allowed_verdicts,
        reasons=(*candidate.reasons, "overridden_by_validation"),
    )


def build_verdict(
    candidate: VerdictCandidate,
    cfg: Config,
    *,
    laya_version: str,
    laya_checkpoint: str,
    question_schema_version: str,
    investigation_id: str,
) -> Verdict:
    """Build the auditable final :class:`Verdict` (spec §4, invariant I14).

    The candidate must already carry the guard's allowed set (see
    :func:`apply_validation`). A verdict outside that set is refused, so nothing
    can leave the allowed verdict space. ``config_version`` is the config hash.
    """
    if candidate.verdict not in candidate.allowed_verdicts:
        raise ValueError(
            f"verdict {candidate.verdict.value} is not in the allowed set "
            f"{sorted(label.value for label in candidate.allowed_verdicts)}"
        )
    return Verdict(
        verdict=candidate.verdict,
        strength=candidate.strength,
        laya_version=laya_version,
        laya_checkpoint=laya_checkpoint,
        question_schema_version=question_schema_version,
        config_version=config_hash(cfg),
        investigation_id=investigation_id,
    )
