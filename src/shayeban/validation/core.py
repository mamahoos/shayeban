"""Pure pre-verdict evidence/budget guard, separate from final model output."""

from dataclasses import dataclass
from enum import StrEnum

from shayeban.weighting import (
    BudgetStatus,
    Stance,
    VerdictCandidate,
    VerdictLabel,
    WeightedEvidence,
    WeightingConfig,
    confirmation_failures,
    evidence_margin,
    has_high_tier_conflict,
)


class ValidationStatus(StrEnum):
    ALLOWED = "allowed"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass(frozen=True)
class ValidationResult:
    status: ValidationStatus
    allowed_verdicts: frozenset[VerdictLabel]
    candidate_permitted: bool
    can_gather_more: bool
    reasons: tuple[str, ...]


def validate(
    candidate: VerdictCandidate,
    weighted: WeightedEvidence,
    *,
    config: WeightingConfig,
    budget: BudgetStatus,
    breaking_mode: bool = False,
) -> ValidationResult:
    """Recheck floors/margin from evidence, not the candidate's claimed label.

    The harness owns numeric query/fetch accounting. Exhaustion plus thin
    evidence leaves UNCLEAR allowed, and never turns a sufficient verdict
    into failure. A review result has no allowed model labels.
    """
    if has_high_tier_conflict(weighted):
        return ValidationResult(
            ValidationStatus.NEEDS_REVIEW,
            frozenset(),
            False,
            False,
            ("high_tier_conflict",),
        )
    allowed = {VerdictLabel.UNCLEAR}
    reasons: tuple[str, ...] = ()
    if evidence_margin(weighted) >= config.margin:
        side = (
            Stance.SUPPORT
            if weighted.support_total > weighted.contradict_total
            else Stance.CONTRADICT
        )
        reasons = confirmation_failures(
            weighted, stance=side, config=config, breaking_mode=breaking_mode
        )
        if not reasons:
            allowed.add(
                VerdictLabel.TRUE if side == Stance.SUPPORT else VerdictLabel.FALSE
            )
    else:
        reasons = ("insufficient_margin",)
    confirmable = len(allowed) > 1
    if not confirmable and budget == BudgetStatus.EXHAUSTED:
        reasons = (*reasons, "budget_exhausted_incomplete")
    return ValidationResult(
        ValidationStatus.ALLOWED,
        frozenset(allowed),
        candidate.verdict in allowed,
        not confirmable and budget == BudgetStatus.AVAILABLE,
        reasons,
    )
