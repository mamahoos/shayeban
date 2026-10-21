"""Frozen data contracts and the Config mirror of ``weights.toml``.

Spec §4 (data contracts) and §11 (config). Everything here is immutable and
free of I/O (invariant I8). Time is never read from a clock: callers pass
``now`` explicitly to the functions in :mod:`shayeban.weighting`.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class SourceTier(StrEnum):
    """Source tier, looked up by domain - never inferred from claim wording (I12)."""

    PRIMARY = "primary"
    JOURNALISM = "journalism"
    FACTCHECK = "factcheck"
    FORUM = "forum"
    UNKNOWN = "unknown"


class Stance(StrEnum):
    """Stance of one evidence item toward the claim (spec §4)."""

    SUPPORT = "support"
    CONTRADICT = "contradict"
    IRRELEVANT = "irrelevant"


class Strength(StrEnum):
    """Worded strength level; the raw score is never stored (ambiguity #3)."""

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


class VerdictLabel(StrEnum):
    """Closed verdict space. UNCLEAR is an answer, not an error (I11)."""

    TRUE = "TRUE"
    FALSE = "FALSE"
    UNCLEAR = "UNCLEAR"
    NEEDS_REVIEW = "NEEDS_REVIEW"


# Tiers that can satisfy the "at least one primary/journalism" floor (spec §8.3).
# Fact-check outlets are weighted like journalism (spec §8.2), so they qualify too.
# Forum is discovery-only and unknown carries zero weight (I12): neither qualifies.
HIGH_TIERS: frozenset[SourceTier] = frozenset(
    {SourceTier.PRIMARY, SourceTier.JOURNALISM, SourceTier.FACTCHECK}
)


@dataclass(frozen=True)
class EvidenceItem:
    """One fetched piece of evidence (spec §4).

    ``derived_count`` is how many copies this item stands for. It informs
    virality only and NEVER enters a weight (spec §8.1, invariant I1).
    """

    url: str
    domain: str
    source_tier: SourceTier
    published_at: datetime | None
    fetched_at: datetime
    snippet: str
    provenance: str
    derived_count: int = 1


@dataclass(frozen=True)
class StancedEvidence:
    """An :class:`EvidenceItem` plus the classifier's stance and confidence."""

    item: EvidenceItem
    stance: Stance
    laya_confidence: float


@dataclass(frozen=True)
class EvidenceGroup:
    """One independent origin after the independence gate (spec §8.1, I2).

    The group contributes exactly ``weight`` regardless of how many items or
    copies it holds: its contribution is capped at its single best item.
    """

    domain: str
    stance: Stance
    source_tier: SourceTier
    weight: float
    is_fresh: bool
    member_count: int
    distinct_content_count: int
    derived_total: int
    urls: tuple[str, ...]


@dataclass(frozen=True)
class WeightedEvidence:
    """Output of the independence gate + weighting (spec §4, §8.2)."""

    groups: tuple[EvidenceGroup, ...]
    support_total: float
    contradict_total: float
    independent_group_count: int

    @property
    def totals_per_stance(self) -> dict[Stance, float]:
        """Per-stance weighted totals, recorded for audit (spec §8.3, I14)."""
        return {
            Stance.SUPPORT: self.support_total,
            Stance.CONTRADICT: self.contradict_total,
        }


@dataclass(frozen=True)
class Thresholds:
    """Effective thresholds for one run, after breaking mode is applied (I13)."""

    min_independent_groups: int
    min_high_tier_groups: int
    margin: float
    require_fresh_high_tier: bool


@dataclass(frozen=True)
class VerdictCandidate:
    """Roll-up result (spec §4, §8.3).

    ``allowed_verdicts`` is empty until :mod:`shayeban.validation` fills it.
    """

    verdict: VerdictLabel
    strength: Strength
    breaking_mode: bool
    allowed_verdicts: frozenset[VerdictLabel] = frozenset()
    support_total: float = 0.0
    contradict_total: float = 0.0
    margin: float = 0.0
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class Verdict:
    """Final auditable verdict record (spec §4, invariant I14)."""

    verdict: VerdictLabel
    strength: Strength
    laya_version: str
    laya_checkpoint: str
    question_schema_version: str
    config_version: str
    investigation_id: str


@dataclass(frozen=True)
class BudgetState:
    """Budget consumed so far (spec §8.4). Exhaustion never means failure (I11)."""

    searches_used: int
    fetches_used: int


@dataclass(frozen=True)
class TierWeights:
    """``[tier_weights]`` - base(tier) of spec §8.2."""

    primary: float
    journalism: float
    factcheck: float
    forum: float
    unknown: float


@dataclass(frozen=True)
class RecencyConfig:
    """``[recency]`` - recency bands of spec §8.2 (ages in hours)."""

    fresh_hours: float
    fresh_factor: float
    aging_hours: float
    aging_factor: float
    stale_factor: float


@dataclass(frozen=True)
class RollupConfig:
    """``[rollup]`` - roll-up thresholds of spec §8.3."""

    margin: float
    min_independent_groups: int
    min_independent_groups_breaking: int
    min_high_tier_groups: int
    strong_margin: float
    strong_min_groups: int
    moderate_margin: float
    moderate_min_groups: int


@dataclass(frozen=True)
class BreakingModeConfig:
    """``[breaking_mode]`` - velocity thresholds used by the caller (spec §11)."""

    high_velocity_15m: int
    low_velocity_1h: int


@dataclass(frozen=True)
class BudgetConfig:
    """``[budget]`` - search/fetch limits (spec §8.4)."""

    max_searches: int
    max_fetches_per_query: int


@dataclass(frozen=True)
class Config:
    """Immutable mirror of ``config/weights.toml`` (spec §11, ambiguity #7)."""

    tier_weights: TierWeights
    recency: RecencyConfig
    rollup: RollupConfig
    breaking_mode: BreakingModeConfig
    budget: BudgetConfig

    def __post_init__(self) -> None:
        """Reject inconsistent thresholds early (fail loudly, never mis-weigh silently)."""
        tw, rc, ro = self.tier_weights, self.recency, self.rollup
        problems: list[str] = []
        numeric_values = (
            tw.primary,
            tw.journalism,
            tw.factcheck,
            tw.forum,
            tw.unknown,
            rc.fresh_hours,
            rc.fresh_factor,
            rc.aging_hours,
            rc.aging_factor,
            rc.stale_factor,
            ro.margin,
            ro.strong_margin,
            ro.moderate_margin,
        )
        integer_values = (
            ro.min_independent_groups,
            ro.min_independent_groups_breaking,
            ro.min_high_tier_groups,
            ro.strong_min_groups,
            ro.moderate_min_groups,
            self.breaking_mode.high_velocity_15m,
            self.breaking_mode.low_velocity_1h,
            self.budget.max_searches,
            self.budget.max_fetches_per_query,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            for value in numeric_values
        ):
            problems.append("all weights and thresholds must be numeric")
        elif any(not math.isfinite(value) for value in numeric_values):
            problems.append("all weights and thresholds must be finite")
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in integer_values
        ):
            problems.append("group counts, velocities, and budgets must be integers")
        if problems:
            raise ValueError("invalid config: " + "; ".join(problems))
        if tw.unknown != 0.0:
            problems.append("tier_weights.unknown must be 0 (invariant I12)")
        high_floor = min(tw.journalism, tw.factcheck)
        if not (
            tw.primary >= max(tw.journalism, tw.factcheck)
            and high_floor >= tw.forum >= tw.unknown >= 0.0
        ):
            problems.append(
                "tier weights must satisfy primary >= journalism/factcheck >= forum >= unknown >= 0"
            )
        if not (0.0 < rc.fresh_hours <= rc.aging_hours):
            problems.append("recency hours must satisfy 0 < fresh_hours <= aging_hours")
        if not (0.0 < rc.stale_factor <= rc.aging_factor <= rc.fresh_factor <= 1.0):
            problems.append(
                "recency factors must satisfy 0 < stale <= aging <= fresh <= 1 (non-zero floor)"
            )
        if not (
            0.0 < ro.margin <= 1.0
            and 0.0 <= ro.moderate_margin <= ro.strong_margin <= 1.0
        ):
            problems.append(
                "rollup margins must lie in [0, 1], margin > 0, moderate_margin <= strong_margin"
            )
        if not (1 <= ro.min_independent_groups <= ro.min_independent_groups_breaking):
            problems.append(
                "need 1 <= min_independent_groups <= min_independent_groups_breaking"
            )
        if ro.min_high_tier_groups < 1:
            problems.append("min_high_tier_groups must be >= 1 (spec §8.3)")
        if not (1 <= ro.moderate_min_groups <= ro.strong_min_groups):
            problems.append("need 1 <= moderate_min_groups <= strong_min_groups")
        if self.budget.max_searches < 1 or self.budget.max_fetches_per_query < 1:
            problems.append("budget limits must be >= 1")
        if (
            self.breaking_mode.high_velocity_15m < 0
            or self.breaking_mode.low_velocity_1h < 0
        ):
            problems.append("breaking_mode velocities must be >= 0")
        if problems:
            raise ValueError("invalid config: " + "; ".join(problems))


def _mapping_section(
    data: Mapping[str, Any], name: str, expected_keys: frozenset[str]
) -> Mapping[str, Any]:
    section = data.get(name)
    if not isinstance(section, Mapping):
        raise TypeError(f"config section {name!r} must be a mapping")
    actual_keys = frozenset(section)
    if actual_keys != expected_keys:
        missing = sorted(expected_keys - actual_keys)
        extra = sorted(actual_keys - expected_keys, key=str)
        raise ValueError(
            f"invalid config section {name!r}: missing keys {missing}, "
            f"unexpected keys {extra}"
        )
    return section


def _float_value(section: Mapping[str, Any], name: str, key: str) -> float:
    value = section[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"config value {name}.{key} must be a number")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"config value {name}.{key} must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"config value {name}.{key} must be finite")
    return result


def _int_value(section: Mapping[str, Any], name: str, key: str) -> int:
    value = section[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"config value {name}.{key} must be an integer")
    return int(value)


def config_from_mapping(data: Mapping[str, Any]) -> Config:
    """Build a :class:`Config` from a parsed TOML mapping (pure, no file access)."""
    expected_sections = frozenset(
        {"tier_weights", "recency", "rollup", "breaking_mode", "budget"}
    )
    actual_sections = frozenset(data)
    if actual_sections != expected_sections:
        missing = sorted(expected_sections - actual_sections)
        extra = sorted(actual_sections - expected_sections, key=str)
        raise ValueError(
            f"invalid config: missing sections {missing}, unexpected sections {extra}"
        )
    tw = _mapping_section(
        data,
        "tier_weights",
        frozenset({"primary", "journalism", "factcheck", "forum", "unknown"}),
    )
    rc = _mapping_section(
        data,
        "recency",
        frozenset(
            {
                "fresh_hours",
                "fresh_factor",
                "aging_hours",
                "aging_factor",
                "stale_factor",
            }
        ),
    )
    ro = _mapping_section(
        data,
        "rollup",
        frozenset(
            {
                "margin",
                "min_independent_groups",
                "min_independent_groups_breaking",
                "min_high_tier_groups",
                "strong_margin",
                "strong_min_groups",
                "moderate_margin",
                "moderate_min_groups",
            }
        ),
    )
    bm = _mapping_section(
        data, "breaking_mode", frozenset({"high_velocity_15m", "low_velocity_1h"})
    )
    bu = _mapping_section(
        data, "budget", frozenset({"max_searches", "max_fetches_per_query"})
    )
    return Config(
        tier_weights=TierWeights(
            primary=_float_value(tw, "tier_weights", "primary"),
            journalism=_float_value(tw, "tier_weights", "journalism"),
            factcheck=_float_value(tw, "tier_weights", "factcheck"),
            forum=_float_value(tw, "tier_weights", "forum"),
            unknown=_float_value(tw, "tier_weights", "unknown"),
        ),
        recency=RecencyConfig(
            fresh_hours=_float_value(rc, "recency", "fresh_hours"),
            fresh_factor=_float_value(rc, "recency", "fresh_factor"),
            aging_hours=_float_value(rc, "recency", "aging_hours"),
            aging_factor=_float_value(rc, "recency", "aging_factor"),
            stale_factor=_float_value(rc, "recency", "stale_factor"),
        ),
        rollup=RollupConfig(
            margin=_float_value(ro, "rollup", "margin"),
            min_independent_groups=_int_value(ro, "rollup", "min_independent_groups"),
            min_independent_groups_breaking=_int_value(
                ro, "rollup", "min_independent_groups_breaking"
            ),
            min_high_tier_groups=_int_value(ro, "rollup", "min_high_tier_groups"),
            strong_margin=_float_value(ro, "rollup", "strong_margin"),
            strong_min_groups=_int_value(ro, "rollup", "strong_min_groups"),
            moderate_margin=_float_value(ro, "rollup", "moderate_margin"),
            moderate_min_groups=_int_value(ro, "rollup", "moderate_min_groups"),
        ),
        breaking_mode=BreakingModeConfig(
            high_velocity_15m=_int_value(bm, "breaking_mode", "high_velocity_15m"),
            low_velocity_1h=_int_value(bm, "breaking_mode", "low_velocity_1h"),
        ),
        budget=BudgetConfig(
            max_searches=_int_value(bu, "budget", "max_searches"),
            max_fetches_per_query=_int_value(bu, "budget", "max_fetches_per_query"),
        ),
    )


def config_hash(config: Config) -> str:
    """Effective-config hash used as ``config_version`` (spec §11, I14)."""
    canonical = json.dumps(asdict(config), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
