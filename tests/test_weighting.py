"""Offline task-13 scenarios: real pure functions, fixed inputs, no mocks/I/O."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import permutations

import pytest

from shayeban.validation import ValidationStatus, validate
from shayeban.weighting import (
    BudgetStatus,
    Evidence,
    SourceTier,
    Stance,
    Strength,
    TierWeights,
    VerdictCandidate,
    VerdictLabel,
    WeightingConfig,
    rollup,
    weight_evidence,
)

NOW = datetime(2026, 10, 21, 12, tzinfo=UTC)
CONFIRMED = {VerdictLabel.TRUE, VerdictLabel.FALSE}


@pytest.fixture
def config() -> WeightingConfig:
    return WeightingConfig(
        tiers=TierWeights(1.0, 0.8, 0.8, 0.05, 0.0),
        fresh_hours=24.0,
        aging_hours=168.0,
        fresh_factor=1.0,
        aging_factor=0.7,
        stale_factor=0.3,
        margin=0.3,
        min_groups=2,
        breaking_min_groups=3,
        min_high_tier_groups=1,
        breaking_window_hours=0.25,
        breaking_min_recent_groups=3,
        moderate_margin=0.4,
        strong_margin=0.6,
        moderate_groups=3,
        strong_groups=4,
    )


def evidence(
    domain: str,
    *,
    tier: SourceTier = SourceTier.JOURNALISM,
    stance: Stance = Stance.SUPPORT,
    confidence: float = 0.9,
    age_hours: float | None = 0.1,
    evidence_id: str | None = None,
    origin_id: str | None = None,
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id or f"report:{domain}",
        domain=domain,
        tier=tier,
        stance=stance,
        confidence=confidence,
        published_at=None if age_hours is None else NOW - timedelta(hours=age_hours),
        origin_id=origin_id,
    )


@pytest.mark.parametrize(
    ("stance", "expected"),
    [(Stance.SUPPORT, VerdictLabel.TRUE), (Stance.CONTRADICT, VerdictLabel.FALSE)],
)
def test_corroborating_sources_confirm(
    config: WeightingConfig, stance: Stance, expected: VerdictLabel
) -> None:
    items = [evidence(domain, stance=stance) for domain in ("a.example", "b.example")]
    weighted = weight_evidence(items, config=config, now=NOW)
    candidate = rollup(weighted, config=config)
    result = validate(candidate, weighted, config=config, budget=BudgetStatus.AVAILABLE)
    assert weighted.independent_groups == 2
    assert candidate.verdict == expected
    assert candidate.strength == Strength.WEAK  # two groups are still thin
    assert result.allowed_verdicts == {VerdictLabel.UNCLEAR, expected}
    assert result.candidate_permitted


@pytest.mark.parametrize("copies", [1, 5, 50])
@pytest.mark.parametrize("stance", [Stance.SUPPORT, Stance.CONTRADICT])
def test_one_domain_times_n_copies_cannot_confirm(
    config: WeightingConfig, copies: int, stance: Stance
) -> None:
    original = evidence("one.example", stance=stance)
    items = [replace(original, evidence_id=f"copy:{i}") for i in range(copies)]
    weighted = weight_evidence(items, config=config, now=NOW)
    candidate = rollup(weighted, config=config)
    result = validate(candidate, weighted, config=config, budget=BudgetStatus.AVAILABLE)
    assert weighted.independent_groups == 1
    assert max(weighted.support_total, weighted.contradict_total) == pytest.approx(0.72)
    assert candidate.verdict == VerdictLabel.UNCLEAR
    assert not CONFIRMED.intersection(result.allowed_verdicts)


@pytest.mark.parametrize(
    "items",
    [
        [],
        [evidence("one.example")],
        [evidence("a.example", tier=SourceTier.UNKNOWN), evidence("b.example")],
        [
            evidence("a.example", tier=SourceTier.FORUM),
            evidence("b.example", tier=SourceTier.FORUM),
        ],
        [evidence("a.example", confidence=0), evidence("b.example", confidence=0)],
        [evidence("a.example", stance=Stance.IRRELEVANT)],
    ],
    ids=[
        "empty",
        "single",
        "unknown_not_independent",
        "forum_only",
        "zero",
        "irrelevant",
    ],
)
def test_thin_evidence_is_unclear(
    config: WeightingConfig, items: list[Evidence]
) -> None:
    weighted = weight_evidence(items, config=config, now=NOW)
    candidate = rollup(weighted, config=config)
    result = validate(candidate, weighted, config=config, budget=BudgetStatus.EXHAUSTED)
    assert candidate.verdict == VerdictLabel.UNCLEAR
    assert candidate.strength == Strength.WEAK
    assert result.allowed_verdicts == {VerdictLabel.UNCLEAR}
    assert result.candidate_permitted
    assert not result.can_gather_more
    assert "budget_exhausted_incomplete" in result.reasons


@pytest.mark.parametrize("budget", list(BudgetStatus))
def test_budget_exhaustion_does_not_veto_sufficient_evidence(
    config: WeightingConfig, budget: BudgetStatus
) -> None:
    weighted = weight_evidence(
        [evidence("a.example"), evidence("b.example")], config=config, now=NOW
    )
    result = validate(
        rollup(weighted, config=config), weighted, config=config, budget=budget
    )
    assert VerdictLabel.TRUE in result.allowed_verdicts
    assert "budget_exhausted_incomplete" not in result.reasons
    assert not result.can_gather_more


def test_thin_evidence_with_budget_can_continue(config: WeightingConfig) -> None:
    weighted = weight_evidence([evidence("one.example")], config=config, now=NOW)
    result = validate(
        rollup(weighted, config=config),
        weighted,
        config=config,
        budget=BudgetStatus.AVAILABLE,
    )
    assert result.can_gather_more


def test_guard_rejects_forged_confirmation(config: WeightingConfig) -> None:
    weighted = weight_evidence([evidence("one.example")], config=config, now=NOW)
    forged = VerdictCandidate(VerdictLabel.TRUE, Strength.STRONG, ())
    result = validate(forged, weighted, config=config, budget=BudgetStatus.AVAILABLE)
    assert not result.candidate_permitted
    assert result.allowed_verdicts == {VerdictLabel.UNCLEAR}


@pytest.mark.parametrize("same_domain", [False, True])
def test_high_tier_conflict_is_a_review_outcome_not_model_label(
    config: WeightingConfig, same_domain: bool
) -> None:
    items = [
        evidence("a.example"),
        evidence(
            "a.example" if same_domain else "b.example",
            stance=Stance.CONTRADICT,
            evidence_id="opposing-report",
        ),
    ]
    weighted = weight_evidence(items, config=config, now=NOW)
    result = validate(
        rollup(weighted, config=config),
        weighted,
        config=config,
        budget=BudgetStatus.AVAILABLE,
    )
    assert result.status == ValidationStatus.NEEDS_REVIEW
    assert not result.allowed_verdicts
    assert not result.candidate_permitted
    assert not result.can_gather_more
    assert weighted.independent_groups <= (0 if same_domain else 2)


def test_same_domain_is_case_and_www_insensitive(config: WeightingConfig) -> None:
    weighted = weight_evidence(
        [evidence("WWW.A.Example."), evidence("a.example")], config=config, now=NOW
    )
    assert len(weighted.groups) == 1
    assert weighted.groups[0].domains == ("a.example",)


def test_known_syndicated_copy_never_increases_weight(config: WeightingConfig) -> None:
    original = evidence("origin.example", confidence=0.1, origin_id="wire:1")
    mirror = evidence("mirror.example", confidence=0.1, origin_id="wire:1")
    before = weight_evidence([original], config=config, now=NOW)
    after = weight_evidence([original, mirror], config=config, now=NOW)
    assert after.support_total <= before.support_total
    assert after.independent_groups == before.independent_groups == 1


def test_repeated_evidence_id_is_not_an_independent_origin(
    config: WeightingConfig,
) -> None:
    original = evidence("one.example")
    duplicate = replace(original, domain="mirror.example")
    weighted = weight_evidence([original, duplicate], config=config, now=NOW)
    assert weighted.independent_groups == 1
    assert weighted.support_total == pytest.approx(0.72)


def test_copy_cannot_change_review_to_true(config: WeightingConfig) -> None:
    original = evidence(
        "origin.example", tier=SourceTier.PRIMARY, confidence=0.1, origin_id="wire:1"
    )
    items = [
        original,
        evidence("news.example"),
        evidence(
            "opposition.example", tier=SourceTier.PRIMARY, stance=Stance.CONTRADICT
        ),
    ]
    mirror = replace(
        original, domain="mirror.example", evidence_id="mirror:1", confidence=1
    )
    before = weight_evidence(items, config=config, now=NOW)
    assert rollup(before, config=config).verdict == VerdictLabel.UNCLEAR
    with pytest.raises(ValueError, match="canonical origin"):
        weight_evidence([*items, mirror], config=config, now=NOW)


def test_transitive_domain_and_origin_links_are_one_group(
    config: WeightingConfig,
) -> None:
    items = [
        evidence("a.example", evidence_id="a:1", origin_id="wire:1"),
        evidence("b.example", evidence_id="b:1", origin_id="wire:1"),
        evidence("b.example", evidence_id="b:2", origin_id="wire:2"),
        evidence("c.example", evidence_id="c:1", origin_id="wire:2"),
    ]
    weighted = weight_evidence(items, config=config, now=NOW)
    assert len(weighted.groups) == 1
    assert weighted.independent_groups == 1


def test_equal_weight_versions_are_order_independent(config: WeightingConfig) -> None:
    fresh = evidence("a.example", confidence=0.7)
    aging = replace(
        fresh,
        evidence_id="distinct-aging-report",
        confidence=1,
        published_at=NOW - timedelta(hours=48),
    )
    items = [fresh, aging, evidence("b.example"), evidence("c.example")]
    reference = weight_evidence(items, config=config, now=NOW)
    for ordered in permutations(items):
        weighted = weight_evidence(ordered, config=config, now=NOW)
        assert weighted == reference
        assert (
            rollup(weighted, config=config, breaking_mode=True).verdict
            == VerdictLabel.UNCLEAR
        )
    assert items[0] == fresh  # no mutation while reducing


@pytest.mark.parametrize(
    ("age", "factor"),
    [
        (0, 1),
        (24, 1),
        (24.001, 0.7),
        (168, 0.7),
        (168.001, 0.3),
        (None, 0.3),
        (-1, 0.3),
    ],
)
def test_recency_bands_and_untrusted_dates(
    config: WeightingConfig, age: float | None, factor: float
) -> None:
    weighted = weight_evidence(
        [evidence("a.example", confidence=0.5, age_hours=age)], config=config, now=NOW
    )
    assert weighted.support_total == pytest.approx(0.8 * 0.5 * factor)


@pytest.mark.parametrize("age", [0.25, 0.251, 23, None, -1])
def test_breaking_uses_its_own_recency_window(
    config: WeightingConfig, age: float | None
) -> None:
    items = [evidence(f"site-{i}.example", age_hours=age) for i in range(3)]
    weighted = weight_evidence(items, config=config, now=NOW)
    candidate = rollup(weighted, config=config, breaking_mode=True)
    result = validate(
        candidate,
        weighted,
        config=config,
        budget=BudgetStatus.AVAILABLE,
        breaking_mode=True,
    )
    if age == 0.25:
        assert candidate.verdict == VerdictLabel.TRUE
        assert VerdictLabel.TRUE in result.allowed_verdicts
    else:
        assert candidate.verdict == VerdictLabel.UNCLEAR
        assert result.allowed_verdicts == {VerdictLabel.UNCLEAR}


@pytest.mark.parametrize("count", [1, 2, 3, 4])
def test_breaking_never_confirms_what_normal_mode_rejects(
    config: WeightingConfig, count: int
) -> None:
    weighted = weight_evidence(
        [evidence(f"site-{i}.example") for i in range(count)], config=config, now=NOW
    )
    normal = rollup(weighted, config=config)
    breaking = rollup(weighted, config=config, breaking_mode=True)
    if breaking.verdict in CONFIRMED:
        assert normal.verdict == breaking.verdict


@pytest.mark.parametrize(
    ("count", "expected"),
    [(2, Strength.WEAK), (3, Strength.MODERATE), (4, Strength.STRONG)],
)
def test_strength_requires_independence_not_just_margin(
    config: WeightingConfig, count: int, expected: Strength
) -> None:
    weighted = weight_evidence(
        [evidence(f"site-{i}.example") for i in range(count)], config=config, now=NOW
    )
    assert rollup(weighted, config=config).strength == expected


@pytest.mark.parametrize("confidence", [float("nan"), float("inf"), -0.01, 1.01])
def test_invalid_confidence_is_rejected(confidence: float) -> None:
    with pytest.raises(ValueError, match="confidence"):
        evidence("a.example", confidence=confidence)


def test_naive_timestamps_are_rejected(config: WeightingConfig) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(evidence("a.example"), published_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="timezone-aware"):
        weight_evidence([], config=config, now=NOW.replace(tzinfo=None))


@pytest.mark.parametrize(
    "domain", ["", "https://a.example", "a.example:443", "a example"]
)
def test_invalid_domain_key_is_rejected(config: WeightingConfig, domain: str) -> None:
    with pytest.raises(ValueError):
        weight_evidence([evidence(domain)], config=config, now=NOW)


def test_config_rejects_nonfinite_and_weakened_breaking_rules(
    config: WeightingConfig,
) -> None:
    with pytest.raises(ValueError, match="finite"):
        replace(config, margin=float("nan"))
    with pytest.raises(ValueError, match="cannot lower"):
        replace(config, breaking_min_groups=1)
    with pytest.raises(ValueError, match="nonzero stale"):
        replace(config, stale_factor=0)
    with pytest.raises(ValueError, match="positive integers"):
        replace(config, min_groups=True)


def test_factcheck_weight_does_not_silently_change_high_tier_floor(
    config: WeightingConfig,
) -> None:
    weighted = weight_evidence(
        [
            evidence("a.example", tier=SourceTier.FACTCHECK),
            evidence("b.example", tier=SourceTier.FACTCHECK),
        ],
        config=config,
        now=NOW,
    )
    assert weighted.support_total > 0
    assert rollup(weighted, config=config).verdict == VerdictLabel.UNCLEAR


@pytest.mark.parametrize("field", ["confidence", "tier", "stance", "published_at"])
def test_inconsistent_copy_metadata_is_not_a_new_vote(
    config: WeightingConfig, field: str
) -> None:
    original = evidence("origin.example", origin_id="wire:1")
    mirror = replace(original, domain="mirror.example", evidence_id="mirror:1")
    if field == "confidence":
        mirror = replace(mirror, confidence=0.01)
    elif field == "tier":
        mirror = replace(mirror, tier=SourceTier.UNKNOWN)
    elif field == "stance":
        mirror = replace(mirror, stance=Stance.IRRELEVANT)
    else:
        mirror = replace(mirror, published_at=NOW - timedelta(hours=48))
    for ordered in ([original, mirror], [mirror, original]):
        with pytest.raises(ValueError, match="canonical origin"):
            weight_evidence(ordered, config=config, now=NOW)


@pytest.mark.parametrize(
    ("margin", "expected"), [(0.33, VerdictLabel.TRUE), (0.34, VerdictLabel.UNCLEAR)]
)
def test_required_margin_is_configurable_and_guarded(
    config: WeightingConfig, margin: float, expected: VerdictLabel
) -> None:
    config = replace(config, margin=margin, tiers=replace(config.tiers, forum=0.4))
    items = [
        evidence("a.example", confidence=1),
        evidence("b.example", confidence=1),
        evidence(
            "c.example", tier=SourceTier.FORUM, confidence=1, stance=Stance.CONTRADICT
        ),
        evidence(
            "d.example", tier=SourceTier.FORUM, confidence=1, stance=Stance.CONTRADICT
        ),
    ]
    weighted = weight_evidence(items, config=config, now=NOW)
    candidate = rollup(weighted, config=config)
    assert candidate.verdict == expected
    result = validate(candidate, weighted, config=config, budget=BudgetStatus.AVAILABLE)
    assert (VerdictLabel.TRUE in result.allowed_verdicts) == (
        expected == VerdictLabel.TRUE
    )
