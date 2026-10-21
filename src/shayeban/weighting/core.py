"""Pure domain-capped weighting. Time and configuration are explicit inputs."""

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime

from .models import (
    Evidence,
    EvidenceGroup,
    SourceTier,
    Stance,
    Strength,
    VerdictCandidate,
    VerdictLabel,
    WeightedEvidence,
    WeightingConfig,
)


def _domain(value: str) -> str:
    # The harness supplies a site-level key; do not guess public suffixes here.
    result = value.strip().lower().rstrip(".").removeprefix("www.")
    if not result or any(char in result for char in "/:@ "):
        raise ValueError("domain must be a normalized site-level host key")
    return result


def _age(item: Evidence, now: datetime) -> float | None:
    if item.published_at is None:
        return None
    hours = (now - item.published_at).total_seconds() / 3600
    return hours if hours >= 0 else None


def _score(item: Evidence, config: WeightingConfig, now: datetime) -> float:
    if item.stance == Stance.IRRELEVANT:
        return 0
    age = _age(item, now)
    factor = config.stale_factor
    if age is not None:
        if age <= config.fresh_hours:
            factor = config.fresh_factor
        elif age <= config.aging_hours:
            factor = config.aging_factor
    return config.tiers.for_tier(item.tier) * item.confidence * factor


def weight_evidence(
    evidence: Sequence[Evidence], *, config: WeightingConfig, now: datetime
) -> WeightedEvidence:
    """Cap each domain/common origin at one contribution, never one per copy.

    Known copies share origin_id and canonical scoring metadata; conflicting
    observations fail explicitly instead of promoting/demoting an origin. Same-domain
    distinct reports may improve that domain's best contribution, never its
    independent count. A domain with opposing usable reports is held as conflict.
    Unknown syndication is deliberately not inferred from untrusted text.
    """
    if now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    observations: dict[
        tuple[str, str], tuple[SourceTier, Stance, float, datetime | None]
    ] = {}
    for item in evidence:
        identities = [("evidence", item.evidence_id)]
        if item.origin_id is not None:
            identities.append(("origin", item.origin_id))
        signature = (item.tier, item.stance, item.confidence, item.published_at)
        for identity in identities:
            if identity in observations and observations[identity] != signature:
                raise ValueError(
                    "copies must preserve canonical origin scoring metadata"
                )
            observations[identity] = signature
    relevant = tuple(item for item in evidence if item.stance != Stance.IRRELEVANT)
    parents = list(range(len(relevant)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    seen: dict[tuple[str, str], int] = {}
    for index, item in enumerate(relevant):
        keys = [("domain", _domain(item.domain))]
        # evidence_id is also an identity: repeated observations aren't new reports.
        keys.append(("evidence", item.evidence_id))
        if item.origin_id is not None:
            keys.append(("origin", item.origin_id))
        for key in keys:
            if key in seen:
                left, right = find(index), find(seen[key])
                parents[max(left, right)] = min(left, right)
            else:
                seen[key] = index

    clusters: dict[int, list[Evidence]] = defaultdict(list)
    for index, item in enumerate(relevant):
        clusters[find(index)].append(item)

    groups: list[EvidenceGroup] = []
    for members in clusters.values():
        # Same ID must not turn into independent proof through different metadata.
        origins: dict[tuple[str, str], list[Evidence]] = defaultdict(list)
        for item in members:
            key = (
                ("origin", item.origin_id)
                if item.origin_id is not None
                else ("evidence", item.evidence_id)
            )
            origins[key].append(item)

        representatives: list[tuple[float, bool, bool, tuple[str, str], Stance]] = []
        for origin, copies in sorted(origins.items()):
            # Identity validation above makes all scoring fields identical.
            item = copies[0]
            weight = _score(item, config, now)
            if weight <= 0:
                continue
            high = item.tier in (SourceTier.PRIMARY, SourceTier.JOURNALISM)
            age = _age(item, now)
            recent = age is not None and age <= config.breaking_window_hours
            representatives.append((weight, high, recent, origin, item.stance))

        stances = {r[4] for r in representatives if r[0] > 0}
        conflicted = len(stances) > 1 or Stance.IRRELEVANT in stances
        # Explicit tie-break: conservative eligibility, then stable origin ID.
        best = min(
            representatives,
            key=lambda r: (-r[0], r[1], r[2], r[3]),
            default=(0.0, False, False, ("", ""), Stance.IRRELEVANT),
        )
        groups.append(
            EvidenceGroup(
                domains=tuple(sorted({_domain(item.domain) for item in members})),
                evidence_ids=tuple(sorted({item.evidence_id for item in members})),
                stance=Stance.IRRELEVANT if conflicted else best[4],
                weight=0.0 if conflicted else best[0],
                high_tier=any(r[1] for r in representatives) if conflicted else best[1],
                recent=best[2],
                conflicted=conflicted,
            )
        )
    return WeightedEvidence(tuple(sorted(groups, key=lambda group: group.domains)))


def confirmation_failures(
    weighted: WeightedEvidence,
    *,
    stance: Stance,
    config: WeightingConfig,
    breaking_mode: bool = False,
) -> tuple[str, ...]:
    """Evidence floors, reusable by the pre-verdict guard without trusting a label."""
    side = [g for g in weighted.groups if g.stance == stance and g.weight > 0]
    minimum = config.breaking_min_groups if breaking_mode else config.min_groups
    reasons: list[str] = []
    if len(side) < minimum:
        reasons.append("insufficient_independent_evidence")
    if sum(g.high_tier for g in side) < config.min_high_tier_groups:
        reasons.append("insufficient_high_tier_evidence")
    if (
        breaking_mode
        and sum(g.recent and g.high_tier for g in side)
        < config.breaking_min_recent_groups
    ):
        reasons.append("insufficient_current_breaking_evidence")
    return tuple(reasons)


def has_high_tier_conflict(weighted: WeightedEvidence) -> bool:
    """Conflicting qualifying origins require review, including one mixed domain."""
    if any(g.conflicted and g.high_tier for g in weighted.groups):
        return True
    return all(
        any(g.stance == side and g.high_tier and g.weight > 0 for g in weighted.groups)
        for side in (Stance.SUPPORT, Stance.CONTRADICT)
    )


def evidence_margin(weighted: WeightedEvidence) -> float:
    total = weighted.support_total + weighted.contradict_total
    return (
        abs(weighted.support_total - weighted.contradict_total) / total if total else 0
    )


def rollup(
    weighted: WeightedEvidence, *, config: WeightingConfig, breaking_mode: bool = False
) -> VerdictCandidate:
    """Produce a candidate, never a final model verdict or lifecycle transition."""
    margin = evidence_margin(weighted)
    if has_high_tier_conflict(weighted):
        return VerdictCandidate(
            VerdictLabel.UNCLEAR, Strength.WEAK, ("high_tier_conflict",)
        )
    if not weighted.independent_groups:
        return VerdictCandidate(
            VerdictLabel.UNCLEAR, Strength.WEAK, ("no_usable_evidence",)
        )
    if margin < config.margin:
        return VerdictCandidate(
            VerdictLabel.UNCLEAR, Strength.WEAK, ("insufficient_margin",)
        )
    side = (
        Stance.SUPPORT
        if weighted.support_total > weighted.contradict_total
        else Stance.CONTRADICT
    )
    failures = confirmation_failures(
        weighted, stance=side, config=config, breaking_mode=breaking_mode
    )
    if failures:
        return VerdictCandidate(VerdictLabel.UNCLEAR, Strength.WEAK, failures)
    count = sum(g.stance == side and g.weight > 0 for g in weighted.groups)
    strength = Strength.WEAK
    if margin >= config.strong_margin and count >= config.strong_groups:
        strength = Strength.STRONG
    elif margin >= config.moderate_margin and count >= config.moderate_groups:
        strength = Strength.MODERATE
    return VerdictCandidate(
        VerdictLabel.TRUE if side == Stance.SUPPORT else VerdictLabel.FALSE,
        strength,
        (),
    )
