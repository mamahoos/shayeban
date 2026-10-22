"""Immutable inputs and results for the offline evidence engine."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite


class SourceTier(StrEnum):
    PRIMARY = "primary"
    JOURNALISM = "journalism"
    FACTCHECK = "factcheck"
    FORUM = "forum"
    UNKNOWN = "unknown"


class Stance(StrEnum):
    SUPPORT = "support"
    CONTRADICT = "contradict"
    IRRELEVANT = "irrelevant"


class VerdictLabel(StrEnum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNCLEAR = "UNCLEAR"


class Strength(StrEnum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


class BudgetStatus(StrEnum):
    """Harness-owned accounting is converted to this status by the caller."""

    AVAILABLE = "available"
    EXHAUSTED = "exhausted"


@dataclass(frozen=True)
class Evidence:
    """A stance-scored item; domain/tier/provenance come from the harness.

    ``domain`` is the caller's site-level independence key, not an arbitrary
    URL. ``origin_id`` identifies known syndicated copies; detecting copies
    and resolving public suffixes are outside this pure core. Copies carry
    their canonical origin's tier, stance, confidence and publication time;
    inconsistent observations are rejected rather than changing the proof.
    """

    evidence_id: str
    domain: str
    tier: SourceTier
    stance: Stance
    confidence: float
    published_at: datetime | None
    origin_id: str | None = None

    def __post_init__(self) -> None:
        if not self.evidence_id.strip() or not self.domain.strip():
            raise ValueError("evidence_id and domain must be nonempty")
        if self.origin_id is not None and not self.origin_id.strip():
            raise ValueError("origin_id must be nonempty when supplied")
        if not isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be finite and between 0 and 1")
        if self.published_at is not None and self.published_at.utcoffset() is None:
            raise ValueError("published_at must be timezone-aware")


@dataclass(frozen=True)
class TierWeights:
    primary: float
    journalism: float
    factcheck: float
    forum: float
    unknown: float

    def __post_init__(self) -> None:
        values = (
            self.primary,
            self.journalism,
            self.factcheck,
            self.forum,
            self.unknown,
        )
        if any(not isfinite(value) or value < 0 for value in values):
            raise ValueError("tier weights must be finite and nonnegative")
        if not (
            self.primary > max(self.journalism, self.factcheck)
            and min(self.journalism, self.factcheck) > self.forum >= self.unknown == 0
        ):
            raise ValueError(
                "tiers require primary > journalism/factcheck > forum >= unknown=0"
            )

    def for_tier(self, tier: SourceTier) -> float:
        return {
            SourceTier.PRIMARY: self.primary,
            SourceTier.JOURNALISM: self.journalism,
            SourceTier.FACTCHECK: self.factcheck,
            SourceTier.FORUM: self.forum,
            SourceTier.UNKNOWN: self.unknown,
        }[tier]


@dataclass(frozen=True)
class WeightingConfig:
    """All tunable scoring, sufficiency and strength numbers, supplied by caller."""

    tiers: TierWeights
    fresh_hours: float
    aging_hours: float
    fresh_factor: float
    aging_factor: float
    stale_factor: float
    margin: float
    min_groups: int
    breaking_min_groups: int
    min_high_tier_groups: int
    breaking_window_hours: float
    breaking_min_recent_groups: int
    moderate_margin: float
    strong_margin: float
    moderate_groups: int
    strong_groups: int

    def __post_init__(self) -> None:
        numbers = (
            self.fresh_hours,
            self.aging_hours,
            self.fresh_factor,
            self.aging_factor,
            self.stale_factor,
            self.margin,
            self.breaking_window_hours,
            self.moderate_margin,
            self.strong_margin,
        )
        counts = (
            self.min_groups,
            self.breaking_min_groups,
            self.min_high_tier_groups,
            self.breaking_min_recent_groups,
            self.moderate_groups,
            self.strong_groups,
        )
        if any(not isfinite(value) for value in numbers):
            raise ValueError("config numbers must be finite")
        if any(type(count) is not int or count < 1 for count in counts):
            raise ValueError("group counts must be positive integers")
        if not 0 < self.fresh_hours <= self.aging_hours:
            raise ValueError("invalid recency bands")
        if not 0 < self.stale_factor <= self.aging_factor <= self.fresh_factor <= 1:
            raise ValueError("recency factors need a nonzero stale floor")
        if not 0 < self.margin <= self.moderate_margin <= self.strong_margin <= 1:
            raise ValueError("invalid confirmation/strength margins")
        if not self.min_groups <= self.moderate_groups <= self.strong_groups:
            raise ValueError("strength counts cannot be below confirmation counts")
        if self.breaking_min_groups < self.min_groups:
            raise ValueError("breaking mode cannot lower the independence floor")
        if self.min_high_tier_groups > self.min_groups:
            raise ValueError("high-tier floor cannot exceed the group floor")
        if not 0 < self.breaking_window_hours <= self.fresh_hours:
            raise ValueError("breaking window must be within the ordinary fresh band")
        if self.breaking_min_recent_groups > self.breaking_min_groups:
            raise ValueError("recent floor cannot exceed breaking group floor")


@dataclass(frozen=True)
class EvidenceGroup:
    """One capped independent group, including known common-origin domains."""

    domains: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    stance: Stance
    weight: float
    high_tier: bool
    recent: bool
    conflicted: bool


@dataclass(frozen=True)
class WeightedEvidence:
    groups: tuple[EvidenceGroup, ...]

    @property
    def support_total(self) -> float:
        return sum(g.weight for g in self.groups if g.stance == Stance.SUPPORT)

    @property
    def contradict_total(self) -> float:
        return sum(g.weight for g in self.groups if g.stance == Stance.CONTRADICT)

    @property
    def independent_groups(self) -> int:
        return sum(g.weight > 0 for g in self.groups)


@dataclass(frozen=True)
class VerdictCandidate:
    verdict: VerdictLabel
    strength: Strength
    reasons: tuple[str, ...]
