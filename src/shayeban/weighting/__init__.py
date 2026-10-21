"""Weighting: independence gate, per-group weights and roll-up (spec §8.1-§8.3).

PURE module (invariant I8): no I/O, no clock, no global state. "Now" is always
an explicit parameter, so the same input always gives the same output.

Pipeline::

    StancedEvidence* --group_by_domain--> clusters      (spec §8.1, I2, ambiguity #1)
                     --build_group------> EvidenceGroup (weight capped per group)
                     --weight_evidence--> WeightedEvidence
                     --rollup-----------> VerdictCandidate (spec §8.3)
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import assert_never

from shayeban.weighting.models import (
    HIGH_TIERS,
    BreakingModeConfig,
    BudgetConfig,
    BudgetState,
    Config,
    EvidenceGroup,
    EvidenceItem,
    RecencyConfig,
    RollupConfig,
    SourceTier,
    Stance,
    StancedEvidence,
    Strength,
    Thresholds,
    TierWeights,
    Verdict,
    VerdictCandidate,
    VerdictLabel,
    WeightedEvidence,
    config_from_mapping,
    config_hash,
)

__all__ = [
    "HIGH_TIERS",
    "BreakingModeConfig",
    "BudgetConfig",
    "BudgetState",
    "Config",
    "EvidenceGroup",
    "EvidenceItem",
    "RecencyConfig",
    "RollupConfig",
    "SourceTier",
    "Stance",
    "StancedEvidence",
    "Strength",
    "Thresholds",
    "TierWeights",
    "Verdict",
    "VerdictCandidate",
    "VerdictLabel",
    "WeightedEvidence",
    "base_weight",
    "build_group",
    "classify_strength",
    "config_from_mapping",
    "config_hash",
    "content_hash",
    "effective_thresholds",
    "floor_failures",
    "group_by_domain",
    "groups_for",
    "is_fresh",
    "item_weight",
    "margin_of",
    "normalize_domain",
    "recency_factor",
    "registrable_domain",
    "rollup",
    "side_meets_floors",
    "weight_evidence",
]


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #


# Common two-label public suffixes (no network or PSL file: this module stays pure).
# Heuristic for ambiguity #1: it keeps ``bbc.co.uk`` and ``isna.ac.ir`` from being
# collapsed into the suffix itself. Unlisted suffixes fall back to the last two labels.
_SECOND_LEVEL_SUFFIXES: frozenset[str] = frozenset(
    {
        "co.uk",
        "org.uk",
        "ac.uk",
        "gov.uk",
        "com.au",
        "org.au",
        "gov.au",
        "edu.au",
        "co.nz",
        "co.jp",
        "co.in",
        "co.za",
        "com.br",
        "com.tr",
        "org.tr",
        "gov.tr",
        "com.cn",
        "com.sa",
        "com.eg",
        "co.il",
        "co.ir",
        "ac.ir",
        "gov.ir",
        "org.ir",
        "sch.ir",
        "net.ir",
        "id.ir",
    }
)


def normalize_domain(domain: str) -> str:
    """Lower-case a host, drop a port and a leading ``www.`` (spec §8.1 grouping key)."""
    cleaned = domain.strip().lower().rstrip(".")
    if not cleaned.startswith("["):
        cleaned = cleaned.split(":", 1)[0]
    return cleaned.removeprefix("www.")


def registrable_domain(domain: str) -> str:
    """Site-level origin of a host: ``a.news.example`` and ``b.news.example`` → ``news.example``.

    Subdomains of one site are one origin (invariant I2, ambiguity #1), so they must
    not count as independent. IP addresses and bare hosts are returned unchanged.
    """
    host = normalize_domain(domain)
    labels = host.split(".")
    if len(labels) <= 2 or labels[-1].isdigit():
        return host
    if ".".join(labels[-2:]) in _SECOND_LEVEL_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _normalized_snippet(snippet: str) -> str:
    return " ".join(snippet.lower().split())


def content_hash(snippet: str) -> str:
    """Hash of whitespace/case-normalised text (ambiguity #1: domain-level + hash)."""
    return hashlib.sha256(_normalized_snippet(snippet).encode("utf-8")).hexdigest()


def _tier_rank(tier: SourceTier) -> int:
    match tier:
        case SourceTier.PRIMARY:
            return 4
        case SourceTier.JOURNALISM | SourceTier.FACTCHECK:
            return 3
        case SourceTier.FORUM:
            return 1
        case SourceTier.UNKNOWN:
            return 0
        case _:
            assert_never(tier)


def margin_of(support_total: float, contradict_total: float) -> float:
    """Relative margin ``|s - c| / (s + c)`` in [0, 1]; 0 when there is no weight."""
    total = support_total + contradict_total
    if total <= 0.0:
        return 0.0
    return abs(support_total - contradict_total) / total


# --------------------------------------------------------------------------- #
# Spec §8.2 - per-item weight
# --------------------------------------------------------------------------- #


def base_weight(tier: SourceTier, weights: TierWeights) -> float:
    """``base(tier)`` from config: primary > journalism ≈ factcheck > forum > unknown (=0)."""
    match tier:
        case SourceTier.PRIMARY:
            return weights.primary
        case SourceTier.JOURNALISM:
            return weights.journalism
        case SourceTier.FACTCHECK:
            return weights.factcheck
        case SourceTier.FORUM:
            return weights.forum
        case SourceTier.UNKNOWN:
            return weights.unknown
        case _:
            assert_never(tier)


def _age_hours(published_at: datetime, now: datetime) -> float:
    if published_at.tzinfo is None or now.tzinfo is None:
        raise ValueError("published_at and now must be timezone-aware datetimes")
    return (now - published_at).total_seconds() / 3600.0


def recency_factor(
    published_at: datetime | None, now: datetime, cfg: RecencyConfig
) -> float:
    """Banded recency factor (spec §8.2): fresh, aging, or a non-zero stale floor.

    ``now`` is injected so the function stays pure. A missing publication date
    is treated as stale (the conservative choice). Timestamps must be
    timezone-aware and comparable with ``now``.
    """
    if published_at is None:
        return cfg.stale_factor
    age_hours = _age_hours(published_at, now)
    if age_hours <= cfg.fresh_hours:
        return cfg.fresh_factor
    if age_hours <= cfg.aging_hours:
        return cfg.aging_factor
    return cfg.stale_factor


def is_fresh(published_at: datetime | None, now: datetime, cfg: RecencyConfig) -> bool:
    """True when the item is inside the fresh band (used by the breaking-mode cross-check)."""
    if published_at is None:
        return False
    return _age_hours(published_at, now) <= cfg.fresh_hours


def item_weight(evidence: StancedEvidence, now: datetime, cfg: Config) -> float:
    """``base(tier) × laya_confidence × recency_factor`` (spec §8.2).

    ``derived_count`` and breaking mode are deliberately absent (I1, I13).
    Irrelevant items weigh nothing; confidence is clamped to [0, 1].
    """
    if evidence.stance is Stance.IRRELEVANT:
        return 0.0
    raw = evidence.laya_confidence
    confidence = 0.0 if math.isnan(raw) else min(1.0, max(0.0, raw))
    return (
        base_weight(evidence.item.source_tier, cfg.tier_weights)
        * confidence
        * recency_factor(evidence.item.published_at, now, cfg.recency)
    )


# --------------------------------------------------------------------------- #
# Spec §8.1 - independence gate
# --------------------------------------------------------------------------- #


def _member_key(evidence: StancedEvidence) -> tuple[str, str, str, str]:
    return (
        registrable_domain(evidence.item.domain),
        evidence.stance.value,
        evidence.item.url,
        content_hash(evidence.item.snippet),
    )


def group_by_domain(
    evidence: Iterable[StancedEvidence],
) -> tuple[tuple[StancedEvidence, ...], ...]:
    """Independence gate (spec §8.1, invariant I2, ambiguity #1).

    Items on the same stance share a group when they come from the same site
    (registrable domain, so subdomains merge),
    or carry identical normalised text (an exact syndicated copy on another
    domain has the same origin). Irrelevant items are dropped. The result does
    not depend on input order.
    """
    relevant = tuple(e for e in evidence if e.stance is not Stance.IRRELEVANT)
    parent = list(range(len(relevant)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    first_seen: dict[tuple[Stance, str, str], int] = {}
    for position, entry in enumerate(relevant):
        keys: list[tuple[Stance, str, str]] = [
            (entry.stance, "domain", registrable_domain(entry.item.domain))
        ]
        if _normalized_snippet(entry.item.snippet):
            keys.append((entry.stance, "content", content_hash(entry.item.snippet)))
        for key in keys:
            earlier = first_seen.get(key)
            if earlier is None:
                first_seen[key] = position
                continue
            root_a, root_b = find(position), find(earlier)
            if root_a != root_b:
                parent[max(root_a, root_b)] = min(root_a, root_b)

    clusters: dict[int, list[StancedEvidence]] = {}
    for position, entry in enumerate(relevant):
        clusters.setdefault(find(position), []).append(entry)

    ordered = [tuple(sorted(members, key=_member_key)) for members in clusters.values()]
    ordered.sort(key=lambda members: tuple(_member_key(m) for m in members))
    return tuple(ordered)


def build_group(
    members: Sequence[StancedEvidence], now: datetime, cfg: Config
) -> EvidenceGroup:
    """Collapse one cluster into a single :class:`EvidenceGroup` (spec §8.1).

    The group's weight is the weight of its single best item, so adding copies
    can never raise it (cap per group, invariant I2). ``derived_total`` is kept
    for virality reporting only (I1).
    """
    best = max(
        members,
        key=lambda m: (
            item_weight(m, now, cfg),
            _tier_rank(m.item.source_tier),
            m.item.url,
        ),
    )
    return EvidenceGroup(
        domain=min(registrable_domain(m.item.domain) for m in members),
        stance=best.stance,
        source_tier=best.item.source_tier,
        weight=item_weight(best, now, cfg),
        is_fresh=is_fresh(best.item.published_at, now, cfg.recency),
        member_count=len(members),
        distinct_content_count=len({content_hash(m.item.snippet) for m in members}),
        derived_total=sum(m.item.derived_count for m in members),
        urls=tuple(sorted(m.item.url for m in members)),
    )


def weight_evidence(
    evidence: Iterable[StancedEvidence], now: datetime, cfg: Config
) -> WeightedEvidence:
    """Run the independence gate FIRST, then sum group weights per stance (spec §8.1-§8.2)."""
    groups = tuple(
        build_group(members, now, cfg) for members in group_by_domain(evidence)
    )
    support = sum(g.weight for g in groups if g.stance is Stance.SUPPORT)
    contradict = sum(g.weight for g in groups if g.stance is Stance.CONTRADICT)
    return WeightedEvidence(
        groups=groups,
        support_total=support,
        contradict_total=contradict,
        independent_group_count=sum(1 for g in groups if g.weight > 0.0),
    )


def groups_for(weighted: WeightedEvidence, stance: Stance) -> tuple[EvidenceGroup, ...]:
    """Groups on *stance* that carry positive weight (zero-weight origins are not independent)."""
    return tuple(g for g in weighted.groups if g.stance is stance and g.weight > 0.0)


# --------------------------------------------------------------------------- #
# Spec §8.3 - thresholds, floors, strength, roll-up
# --------------------------------------------------------------------------- #


def effective_thresholds(cfg: Config, breaking_mode: bool) -> Thresholds:
    """Thresholds for this run. Breaking mode only ever raises a bar (spec §8.3, I13).

    ``max`` guarantees monotonicity even if the config is tuned oddly.
    """
    base_groups = cfg.rollup.min_independent_groups
    groups = (
        max(base_groups, cfg.rollup.min_independent_groups_breaking)
        if breaking_mode
        else base_groups
    )
    return Thresholds(
        min_independent_groups=groups,
        min_high_tier_groups=cfg.rollup.min_high_tier_groups,
        margin=cfg.rollup.margin,
        require_fresh_high_tier=breaking_mode,
    )


def floor_failures(
    weighted: WeightedEvidence, stance: Stance, thresholds: Thresholds
) -> tuple[str, ...]:
    """Stable reason codes for the minimum bars a confirming side must clear (spec §8.3)."""
    side = groups_for(weighted, stance)
    high = tuple(g for g in side if g.source_tier in HIGH_TIERS)
    failures: list[str] = []
    if len(side) < thresholds.min_independent_groups:
        failures.append("too_few_independent_groups")
    if len(high) < thresholds.min_high_tier_groups:
        failures.append("no_high_tier_group")
    if thresholds.require_fresh_high_tier and not any(g.is_fresh for g in high):
        failures.append("no_fresh_high_tier_group")
    return tuple(failures)


def side_meets_floors(
    weighted: WeightedEvidence, stance: Stance, thresholds: Thresholds
) -> bool:
    """True when *stance* has enough independent, high-tier (and, if breaking, fresh) groups."""
    return not floor_failures(weighted, stance, thresholds)


def classify_strength(margin: float, group_count: int, cfg: RollupConfig) -> Strength:
    """Worded strength (spec §8.3, ambiguity #3). A wide margin on thin evidence stays WEAK."""
    if margin >= cfg.strong_margin and group_count >= cfg.strong_min_groups:
        return Strength.STRONG
    if margin >= cfg.moderate_margin and group_count >= cfg.moderate_min_groups:
        return Strength.MODERATE
    return Strength.WEAK


def _has_high_tier(groups: Sequence[EvidenceGroup]) -> bool:
    return any(g.source_tier in HIGH_TIERS for g in groups)


def rollup(
    weighted: WeightedEvidence, cfg: Config, breaking_mode: bool = False
) -> VerdictCandidate:
    """Turn weighted evidence into a :class:`VerdictCandidate` (spec §8.3).

    * Dominant stance must win by ``rollup.margin``; otherwise UNCLEAR, or
      NEEDS_REVIEW when both sides have high-tier evidence (contradiction).
    * TRUE/FALSE additionally need the evidence floors (I2, I3): thin or
      forum-only evidence is UNCLEAR, never FALSE.
    * Breaking mode is an input that raises bars, never a truth signal (I13).
    * Per-stance contributions are recorded on the candidate (I14).
    """
    support = weighted.support_total
    contradict = weighted.contradict_total
    margin = margin_of(support, contradict)
    thresholds = effective_thresholds(cfg, breaking_mode)
    support_groups = groups_for(weighted, Stance.SUPPORT)
    contradict_groups = groups_for(weighted, Stance.CONTRADICT)
    contested = _has_high_tier(support_groups) and _has_high_tier(contradict_groups)

    def candidate(
        verdict: VerdictLabel, strength: Strength, reasons: tuple[str, ...]
    ) -> VerdictCandidate:
        return VerdictCandidate(
            verdict=verdict,
            strength=strength,
            breaking_mode=breaking_mode,
            support_total=support,
            contradict_total=contradict,
            margin=margin,
            reasons=reasons,
        )

    if support + contradict <= 0.0:
        return candidate(VerdictLabel.UNCLEAR, Strength.WEAK, ("no_usable_evidence",))

    if support == contradict or margin < thresholds.margin:
        if contested:
            return candidate(
                VerdictLabel.NEEDS_REVIEW,
                Strength.WEAK,
                ("margin_below_threshold", "contradictory_high_tier"),
            )
        return candidate(
            VerdictLabel.UNCLEAR, Strength.WEAK, ("margin_below_threshold",)
        )

    dominant = Stance.SUPPORT if support > contradict else Stance.CONTRADICT
    failures = floor_failures(weighted, dominant, thresholds)
    if failures:
        return candidate(VerdictLabel.UNCLEAR, Strength.WEAK, failures)

    dominant_groups = (
        support_groups if dominant is Stance.SUPPORT else contradict_groups
    )
    strength = classify_strength(margin, len(dominant_groups), cfg.rollup)
    reasons: tuple[str, ...] = ("dominant_stance_cleared_floors",)
    if contested:
        strength = Strength.WEAK
        reasons = (*reasons, "contradictory_high_tier_caps_strength")
    verdict = VerdictLabel.TRUE if dominant is Stance.SUPPORT else VerdictLabel.FALSE
    return candidate(verdict, strength, reasons)
