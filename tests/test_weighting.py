"""Task 13 tests: weighting + validation, pure core, no mocks, no I/O in the code under test.

Run: ``uv run pytest tests/test_weighting.py -v``
"""

from __future__ import annotations

import ast
import random
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from shayeban import load_config
from shayeban.validation import (
    apply_validation,
    budget_exhausted,
    build_verdict,
    validate,
)
from shayeban.weighting import (
    BreakingModeConfig,
    BudgetConfig,
    BudgetState,
    Config,
    EvidenceItem,
    RecencyConfig,
    RollupConfig,
    SourceTier,
    Stance,
    StancedEvidence,
    Strength,
    TierWeights,
    VerdictCandidate,
    VerdictLabel,
    WeightedEvidence,
    config_from_mapping,
    config_hash,
    effective_thresholds,
    group_by_domain,
    item_weight,
    recency_factor,
    registrable_domain,
    rollup,
    weight_evidence,
)

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
FRESH_BUDGET = BudgetState(searches_used=0, fetches_used=0)
CONFIRMED = {VerdictLabel.TRUE, VerdictLabel.FALSE}
P, J, F, FO, U = (
    SourceTier.PRIMARY,
    SourceTier.JOURNALISM,
    SourceTier.FACTCHECK,
    SourceTier.FORUM,
    SourceTier.UNKNOWN,
)
SUP, CON = Stance.SUPPORT, Stance.CONTRADICT


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def cfg() -> Config:
    """Mirror of config/weights.toml, built by hand (also checked against the file below)."""
    return Config(
        tier_weights=TierWeights(
            primary=1.0, journalism=0.8, factcheck=0.8, forum=0.15, unknown=0.0
        ),
        recency=RecencyConfig(
            fresh_hours=24.0,
            fresh_factor=1.0,
            aging_hours=168.0,
            aging_factor=0.7,
            stale_factor=0.3,
        ),
        rollup=RollupConfig(
            margin=0.30,
            min_independent_groups=2,
            min_independent_groups_breaking=3,
            min_high_tier_groups=1,
            strong_margin=0.60,
            strong_min_groups=4,
            moderate_margin=0.40,
            moderate_min_groups=3,
        ),
        breaking_mode=BreakingModeConfig(high_velocity_15m=20, low_velocity_1h=5),
        budget=BudgetConfig(max_searches=6, max_fetches_per_query=5),
    )


def ev(
    domain: str,
    tier: SourceTier = SourceTier.JOURNALISM,
    stance: Stance = Stance.SUPPORT,
    conf: float = 0.9,
    age_hours: float | None = 1.0,
    url: str | None = None,
    snippet: str | None = None,
    derived: int = 1,
) -> StancedEvidence:
    """Build one StancedEvidence quickly; snippets are unique unless given."""
    link = url if url is not None else f"https://{domain}/article"
    text = (
        snippet if snippet is not None else f"original reporting by {domain} at {link}"
    )
    published = None if age_hours is None else NOW - timedelta(hours=age_hours)
    item = EvidenceItem(
        url=link,
        domain=domain,
        source_tier=tier,
        published_at=published,
        fetched_at=NOW,
        snippet=text,
        provenance="fixture",
        derived_count=derived,
    )
    return StancedEvidence(item=item, stance=stance, laya_confidence=conf)


def run(
    evidence: list[StancedEvidence],
    breaking: bool = False,
    budget: BudgetState = FRESH_BUDGET,
) -> tuple[WeightedEvidence, VerdictCandidate]:
    weighted = weight_evidence(evidence, NOW, cfg())
    candidate = rollup(weighted, cfg(), breaking_mode=breaking)
    return weighted, candidate


# --------------------------------------------------------------------------- #
# Acceptance scenarios (table-driven)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("stance", "expected"),
    [(SUP, VerdictLabel.TRUE), (CON, VerdictLabel.FALSE)],
    ids=["supporting_sources_confirm_true", "contradicting_sources_confirm_false"],
)
def test_corroborating_sources_yield_confirmed_class(
    stance: Stance, expected: VerdictLabel
) -> None:
    evidence = [
        ev("gov.example", P, stance),
        ev("news-a.example", J, stance),
        ev("news-b.example", J, stance),
        ev("checkers.example", F, stance),
    ]
    weighted, candidate = run(evidence)
    result = validate(weighted, candidate, cfg(), FRESH_BUDGET)

    assert weighted.independent_group_count == 4
    assert candidate.verdict is expected
    assert candidate.verdict in CONFIRMED
    assert candidate.strength is Strength.STRONG
    assert expected in result.allowed_verdicts
    assert result.candidate_permitted


@pytest.mark.parametrize("copies", [2, 5, 20])
def test_one_source_n_copies_not_confirmed(copies: int) -> None:
    """Invariant I2: N copies from one origin are ONE independent group."""
    evidence = [
        ev(
            "wire.example",
            P,
            url=f"https://wire.example/copy-{n}",
            snippet=f"the same story, copy {n}",
            derived=10,
        )
        for n in range(copies)
    ]
    weighted, candidate = run(evidence)
    result = validate(weighted, candidate, cfg(), FRESH_BUDGET)

    assert len(weighted.groups) == 1
    assert weighted.independent_group_count == 1
    assert candidate.verdict not in CONFIRMED
    assert candidate.verdict is VerdictLabel.UNCLEAR
    assert VerdictLabel.TRUE not in result.allowed_verdicts
    assert VerdictLabel.FALSE not in result.allowed_verdicts


def test_one_story_syndicated_across_domains_is_still_one_group() -> None:
    """Invariant I2 / ambiguity #1: identical text on other domains shares one origin."""
    story = "Ministry says the bridge reopens on Monday."
    evidence = [ev(f"outlet-{n}.example", J, snippet=story) for n in range(5)]
    weighted, candidate = run(evidence)

    assert len(weighted.groups) == 1
    assert candidate.verdict is VerdictLabel.UNCLEAR


@pytest.mark.parametrize(
    "evidence",
    [
        [],
        [ev("news-a.example", J)],
        [ev("gov.example", P, conf=0.99)],
        [
            ev("forum-a.example", FO),
            ev("forum-b.example", FO),
            ev("forum-c.example", FO),
        ],
        [ev("news-a.example", J, conf=0.0), ev("news-b.example", J, conf=0.0)],
        [ev("blog.example", U), ev("other.example", U)],
        [
            ev("news-a.example", J, stance=Stance.IRRELEVANT),
            ev("news-b.example", J, stance=Stance.IRRELEVANT),
        ],
    ],
    ids=[
        "no_evidence",
        "single_journalism_source",
        "single_primary_source",
        "forum_only",
        "zero_confidence",
        "unknown_tier_only",
        "irrelevant_only",
    ],
)
def test_thin_evidence_yields_unclear_or_needs_review(
    evidence: list[StancedEvidence],
) -> None:
    weighted, candidate = run(evidence)
    result = validate(weighted, candidate, cfg(), FRESH_BUDGET)

    assert candidate.verdict in {VerdictLabel.UNCLEAR, VerdictLabel.NEEDS_REVIEW}
    assert candidate.verdict not in CONFIRMED
    assert CONFIRMED.isdisjoint(result.allowed_verdicts)
    assert result.candidate_permitted


# --------------------------------------------------------------------------- #
# Property tests (spec §8.6)
# --------------------------------------------------------------------------- #


def _base_fixture() -> list[StancedEvidence]:
    return [
        ev("gov.example", P, SUP),
        ev("news-a.example", J, SUP, conf=0.7, age_hours=48.0),
        ev("checkers.example", F, CON, conf=0.6),
        ev("forum-a.example", FO, SUP),
    ]


def _copy_exact(e: StancedEvidence) -> StancedEvidence:
    return e


def _copy_same_domain_lower_confidence(e: StancedEvidence) -> StancedEvidence:
    item = replace(
        e.item,
        url=e.item.url + "?amp",
        snippet="rewritten restatement",
        derived_count=50,
    )
    return replace(e, item=item, laya_confidence=e.laya_confidence * 0.5)


def _copy_verbatim_on_other_domain(e: StancedEvidence) -> StancedEvidence:
    return replace(
        e, item=replace(e.item, domain="mirror.example", url="https://mirror.example/x")
    )


@pytest.mark.parametrize(
    "make_copy",
    [_copy_exact, _copy_same_domain_lower_confidence, _copy_verbatim_on_other_domain],
    ids=[
        "exact_duplicate",
        "same_domain_lower_confidence_copy",
        "other_domain_verbatim_copy",
    ],
)
def test_adding_a_copy_never_increases_totals(
    make_copy: Callable[[StancedEvidence], StancedEvidence],
) -> None:
    before = weight_evidence(_base_fixture(), NOW, cfg())
    for original in _base_fixture():
        after = weight_evidence([*_base_fixture(), make_copy(original)], NOW, cfg())
        assert after.support_total <= before.support_total + 1e-12
        assert after.contradict_total <= before.contradict_total + 1e-12
        assert after.independent_group_count <= before.independent_group_count


@pytest.mark.parametrize("stance", [SUP, CON])
@pytest.mark.parametrize("domains", [1, 2, 3, 12])
def test_forum_only_evidence_never_yields_true(stance: Stance, domains: int) -> None:
    evidence = [ev(f"forum-{n}.example", FO, stance, conf=1.0) for n in range(domains)]
    weighted, candidate = run(evidence)
    result = validate(weighted, candidate, cfg(), FRESH_BUDGET)

    assert candidate.verdict is not VerdictLabel.TRUE
    assert candidate.verdict is not VerdictLabel.FALSE
    assert result.allowed_verdicts <= {VerdictLabel.UNCLEAR}


def test_breaking_mode_never_lowers_a_threshold() -> None:
    normal = effective_thresholds(cfg(), breaking_mode=False)
    breaking = effective_thresholds(cfg(), breaking_mode=True)

    assert breaking.min_independent_groups >= normal.min_independent_groups
    assert breaking.min_high_tier_groups >= normal.min_high_tier_groups
    assert breaking.margin >= normal.margin
    assert breaking.require_fresh_high_tier >= normal.require_fresh_high_tier


def test_breaking_mode_never_confirms_what_normal_mode_would_not() -> None:
    generator = random.Random(13)
    tiers = [P, J, F, FO, U]
    for _ in range(200):
        evidence = [
            ev(
                f"site-{n}.example",
                generator.choice(tiers),
                generator.choice([SUP, CON, Stance.IRRELEVANT]),
                conf=generator.random(),
                age_hours=generator.choice([1.0, 100.0, 1000.0, None]),
            )
            for n in range(generator.randint(0, 6))
        ]
        weighted, normal = run(evidence, breaking=False)
        _, breaking = run(evidence, breaking=True)
        if breaking.verdict in CONFIRMED:
            assert normal.verdict is breaking.verdict
        normal_allowed = validate(
            weighted, normal, cfg(), FRESH_BUDGET
        ).allowed_verdicts
        breaking_allowed = validate(
            weighted, breaking, cfg(), FRESH_BUDGET
        ).allowed_verdicts
        assert (breaking_allowed & CONFIRMED) <= (normal_allowed & CONFIRMED)


def test_breaking_mode_needs_three_groups_and_a_fresh_high_tier_source() -> None:
    two = [ev("gov.example", P), ev("news-a.example", J)]
    three_fresh = [*two, ev("news-b.example", J)]
    three_stale = [
        ev(d, J, age_hours=500.0) for d in ("a.example", "b.example", "c.example")
    ]

    assert run(two)[1].verdict is VerdictLabel.TRUE
    assert run(two, breaking=True)[1].verdict is VerdictLabel.UNCLEAR
    assert run(three_fresh, breaking=True)[1].verdict is VerdictLabel.TRUE
    stale_candidate = run(three_stale, breaking=True)[1]
    assert stale_candidate.verdict is VerdictLabel.UNCLEAR
    assert "no_fresh_high_tier_group" in stale_candidate.reasons


@pytest.mark.parametrize("copies", [1, 5, 50])
def test_one_source_times_five_copies_does_not_confirm(copies: int) -> None:
    single = weight_evidence([ev("gov.example", P)], NOW, cfg())
    many = [
        ev(
            "gov.example",
            P,
            url=f"https://gov.example/{n}",
            snippet=f"text {n}",
            derived=5,
        )
        for n in range(copies)
    ]
    weighted, candidate = run(many)

    assert weighted.support_total == pytest.approx(single.support_total)
    assert weighted.independent_group_count == 1
    assert candidate.verdict not in CONFIRMED


@pytest.mark.parametrize(
    ("support", "contradict"),
    [
        (
            [ev("gov.example", P), ev("news-a.example", J)],
            [ev("news-b.example", J, CON), ev("checkers.example", F, CON)],
        ),
        ([ev("gov.example", P)], [ev("checkers.example", F, CON)]),
        (
            [ev("gov.example", P), ev("news-a.example", J), ev("news-b.example", J)],
            [
                ev("gov2.example", P, CON),
                ev("news-c.example", J, CON),
                ev("news-d.example", J, CON),
            ],
        ),
    ],
    ids=["two_vs_two", "one_vs_one", "three_vs_three"],
)
def test_contradiction_forces_unclear_or_needs_review(
    support: list[StancedEvidence], contradict: list[StancedEvidence]
) -> None:
    weighted, candidate = run([*support, *contradict])
    result = validate(weighted, candidate, cfg(), FRESH_BUDGET)

    assert candidate.verdict in {VerdictLabel.UNCLEAR, VerdictLabel.NEEDS_REVIEW}
    assert result.needs_review
    assert result.allowed_verdicts == {VerdictLabel.NEEDS_REVIEW}


def test_same_inputs_give_same_outputs_regardless_of_order() -> None:
    evidence = _base_fixture() + [ev("news-b.example", J, SUP, derived=7)]
    reference = run(evidence)
    for seed in range(10):
        shuffled = list(evidence)
        random.Random(seed).shuffle(shuffled)
        assert run(shuffled) == reference
    assert run(evidence) == reference
    assert validate(*reference, cfg(), FRESH_BUDGET) == validate(
        *reference, cfg(), FRESH_BUDGET
    )


# --------------------------------------------------------------------------- #
# Weighting details
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("age_hours", "expected"),
    [
        (None, 0.3),
        (-5.0, 1.0),
        (0.0, 1.0),
        (24.0, 1.0),
        (24.1, 0.7),
        (168.0, 0.7),
        (168.1, 0.3),
        (9999.0, 0.3),
    ],
)
def test_recency_bands(age_hours: float | None, expected: float) -> None:
    published = None if age_hours is None else NOW - timedelta(hours=age_hours)
    assert recency_factor(published, NOW, cfg().recency) == expected
    assert expected > 0.0


def test_item_weight_is_tier_times_confidence_times_recency() -> None:
    assert item_weight(
        ev("a.example", P, conf=0.5, age_hours=1.0), NOW, cfg()
    ) == pytest.approx(0.5)
    assert item_weight(
        ev("a.example", J, conf=0.5, age_hours=48.0), NOW, cfg()
    ) == pytest.approx(0.8 * 0.5 * 0.7)
    assert item_weight(
        ev("a.example", FO, conf=1.0, age_hours=900.0), NOW, cfg()
    ) == pytest.approx(0.15 * 0.3)


def test_unknown_tier_carries_zero_weight() -> None:
    """Invariant I12: tier comes from the domain lookup; unknown means no weight."""
    weighted = weight_evidence([ev("mystery.example", U, conf=1.0)], NOW, cfg())
    assert weighted.support_total == 0.0
    assert weighted.independent_group_count == 0


def test_virality_never_changes_weight() -> None:
    """Invariant I1: derived_count informs virality only."""
    quiet = weight_evidence([ev("gov.example", P, derived=1)], NOW, cfg())
    viral = weight_evidence([ev("gov.example", P, derived=1_000_000)], NOW, cfg())
    assert quiet.support_total == viral.support_total
    assert viral.groups[0].derived_total == 1_000_000


def test_domain_grouping_ignores_case_and_www() -> None:
    clusters = group_by_domain(
        [
            ev("News.Example", J, url="https://a"),
            ev("www.news.example", J, url="https://b"),
        ]
    )
    assert len(clusters) == 1


def test_same_domain_on_opposite_stances_stays_two_groups() -> None:
    weighted = weight_evidence(
        [
            ev("news.example", J, SUP, url="https://a"),
            ev("news.example", J, CON, url="https://b"),
        ],
        NOW,
        cfg(),
    )
    assert len(weighted.groups) == 2


def test_group_contribution_is_capped_at_its_best_item() -> None:
    items = [
        ev("news.example", J, conf=0.4, url="https://n/1", snippet="one"),
        ev("news.example", J, conf=0.9, url="https://n/2", snippet="two"),
        ev("news.example", J, conf=0.6, url="https://n/3", snippet="three"),
    ]
    weighted = weight_evidence(items, NOW, cfg())
    assert weighted.support_total == pytest.approx(0.8 * 0.9)
    assert weighted.groups[0].member_count == 3


@pytest.mark.parametrize(
    ("evidence", "expected"),
    [
        ([ev("gov.example", P), ev("news-a.example", J)], Strength.WEAK),
        (
            [ev("gov.example", P), ev("news-a.example", J), ev("news-b.example", J)],
            Strength.MODERATE,
        ),
        (
            [
                ev("gov.example", P),
                ev("news-a.example", J),
                ev("news-b.example", J),
                ev("checkers.example", F),
            ],
            Strength.STRONG,
        ),
    ],
    ids=[
        "wide_margin_thin_evidence_is_weak",
        "three_groups_moderate",
        "four_groups_strong",
    ],
)
def test_strength_is_worded_and_thin_evidence_stays_weak(
    evidence: list[StancedEvidence], expected: Strength
) -> None:
    _, candidate = run(evidence)
    assert candidate.verdict is VerdictLabel.TRUE
    assert candidate.margin == pytest.approx(1.0)
    assert candidate.strength is expected


def test_candidate_records_per_stance_contributions() -> None:
    weighted, candidate = run(_base_fixture())
    assert candidate.support_total == weighted.support_total
    assert candidate.contradict_total == weighted.contradict_total
    assert weighted.totals_per_stance[SUP] == weighted.support_total


def test_absence_of_confirmation_is_not_falsification() -> None:
    """Invariant I3: a single contradicting forum post never produces FALSE."""
    _, candidate = run([ev("forum-a.example", FO, CON, conf=1.0)])
    assert candidate.verdict is VerdictLabel.UNCLEAR


# --------------------------------------------------------------------------- #
# Validation details
# --------------------------------------------------------------------------- #


def test_validation_allows_true_only_when_floors_are_cleared() -> None:
    weighted, candidate = run([ev("gov.example", P), ev("news-a.example", J)])
    result = validate(weighted, candidate, cfg(), FRESH_BUDGET)
    assert result.allowed_verdicts == {VerdictLabel.UNCLEAR, VerdictLabel.TRUE}
    assert not result.needs_review


def test_validation_always_permits_the_rollup_candidate() -> None:
    generator = random.Random(7)
    tiers = [P, J, F, FO, U]
    for _ in range(300):
        evidence = [
            ev(
                f"site-{n}.example",
                generator.choice(tiers),
                generator.choice([SUP, CON, Stance.IRRELEVANT]),
                conf=generator.random(),
                age_hours=generator.choice([1.0, 100.0, 1000.0, None]),
            )
            for n in range(generator.randint(0, 7))
        ]
        for breaking in (False, True):
            weighted, candidate = run(evidence, breaking=breaking)
            result = validate(weighted, candidate, cfg(), FRESH_BUDGET)
            assert result.candidate_permitted
            assert apply_validation(candidate, result).verdict is candidate.verdict


def test_apply_validation_overrides_a_verdict_outside_the_allowed_set() -> None:
    weighted, _ = run([ev("news-a.example", J)])
    forged = VerdictCandidate(VerdictLabel.TRUE, Strength.STRONG, breaking_mode=False)
    result = validate(weighted, forged, cfg(), FRESH_BUDGET)
    fixed = apply_validation(forged, result)

    assert not result.candidate_permitted
    assert fixed.verdict is VerdictLabel.UNCLEAR
    assert fixed.strength is Strength.WEAK
    assert fixed.allowed_verdicts == {VerdictLabel.UNCLEAR}


@pytest.mark.parametrize(
    ("searches", "fetches", "exhausted"),
    [(0, 0, False), (5, 4, False), (6, 0, True), (0, 5, True), (9, 9, True)],
)
def test_budget_exhaustion_rule(searches: int, fetches: int, exhausted: bool) -> None:
    assert budget_exhausted(BudgetState(searches, fetches), cfg().budget) is exhausted


def test_budget_exhausted_with_thin_evidence_is_unclear_not_rejected() -> None:
    """Ambiguity #6: out of budget after thin evidence is an UNCLEAR answer (I11)."""
    weighted, candidate = run([ev("news-a.example", J)])
    spent = BudgetState(searches_used=6, fetches_used=5)
    result = validate(weighted, candidate, cfg(), spent)

    assert result.allowed_verdicts == {VerdictLabel.UNCLEAR}
    assert not result.needs_review
    assert not result.evidence_gathering_open
    assert "budget_exhausted" in result.reasons


def test_thin_evidence_with_budget_left_keeps_gathering_open() -> None:
    weighted, candidate = run([ev("news-a.example", J)])
    result = validate(weighted, candidate, cfg(), FRESH_BUDGET)
    assert result.evidence_gathering_open


def test_budget_exhaustion_never_blocks_a_well_supported_verdict() -> None:
    weighted, candidate = run([ev("gov.example", P), ev("news-a.example", J)])
    result = validate(weighted, candidate, cfg(), BudgetState(6, 5))
    assert VerdictLabel.TRUE in result.allowed_verdicts


# --------------------------------------------------------------------------- #
# Hardening: subdomains, bad input, config validation, auditable verdict
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("host", "site"),
    [
        ("news.example", "news.example"),
        ("WWW.News.Example", "news.example"),
        ("a.b.news.example", "news.example"),
        ("news.example:443", "news.example"),
        ("bbc.co.uk", "bbc.co.uk"),
        ("www.bbc.co.uk", "bbc.co.uk"),
        ("isna.ac.ir", "isna.ac.ir"),
        ("en.isna.ac.ir", "isna.ac.ir"),
        ("10.0.0.1", "10.0.0.1"),
        ("localhost", "localhost"),
    ],
)
def test_registrable_domain_collapses_subdomains(host: str, site: str) -> None:
    assert registrable_domain(host) == site


def test_subdomains_of_one_site_are_one_independent_group() -> None:
    """Invariant I2: a.site and b.site are one origin, not two corroborating sources."""
    evidence = [ev(f"{prefix}.news.example", J) for prefix in ("a", "b", "c", "www")]
    weighted, candidate = run(evidence)
    assert len(weighted.groups) == 1
    assert candidate.verdict is VerdictLabel.UNCLEAR


def test_different_sites_under_one_public_suffix_stay_independent() -> None:
    weighted = weight_evidence(
        [ev("bbc.co.uk", J), ev("guardian.co.uk", J)], NOW, cfg()
    )
    assert len(weighted.groups) == 2


def test_naive_timestamps_are_rejected_clearly() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        recency_factor(datetime(2026, 10, 16, 12, 0), NOW, cfg().recency)


def test_nan_confidence_weighs_nothing() -> None:
    assert item_weight(ev("gov.example", P, conf=float("nan")), NOW, cfg()) == 0.0


@pytest.mark.parametrize(
    "change",
    [
        {"tier_weights": TierWeights(1.0, 0.8, 0.8, 0.15, 0.1)},
        {"tier_weights": TierWeights(0.5, 0.8, 0.8, 0.15, 0.0)},
        {"recency": RecencyConfig(24.0, 1.0, 168.0, 0.7, 0.0)},
        {"recency": RecencyConfig(200.0, 1.0, 168.0, 0.7, 0.3)},
        {"budget": BudgetConfig(max_searches=0, max_fetches_per_query=5)},
    ],
    ids=[
        "unknown_not_zero",
        "primary_below_journalism",
        "no_stale_floor",
        "bad_hour_bands",
        "zero_budget",
    ],
)
def test_invalid_config_is_rejected(change: dict[str, object]) -> None:
    base = cfg()
    fields: dict[str, object] = {
        "tier_weights": base.tier_weights,
        "recency": base.recency,
        "rollup": base.rollup,
        "breaking_mode": base.breaking_mode,
        "budget": base.budget,
    }
    fields.update(change)
    with pytest.raises(ValueError, match="invalid config"):
        Config(**fields)  # type: ignore[arg-type]


def test_config_mapping_rejects_unknown_keys_and_fractional_thresholds() -> None:
    mapping = asdict(cfg())
    mapping["rollup"]["min_independent_groups"] = 2.5
    with pytest.raises(TypeError, match="must be an integer"):
        config_from_mapping(mapping)

    mapping = asdict(cfg())
    mapping["rollup"]["unrecognized_threshold"] = 0.2
    with pytest.raises(ValueError, match="unexpected keys"):
        config_from_mapping(mapping)


def test_non_finite_config_weights_are_rejected() -> None:
    base = cfg()
    with pytest.raises(ValueError, match="must be finite"):
        Config(
            TierWeights(float("inf"), 0.8, 0.8, 0.15, 0.0),
            base.recency,
            base.rollup,
            base.breaking_mode,
            base.budget,
        )
    with pytest.raises(ValueError, match="must be integers"):
        Config(
            base.tier_weights,
            base.recency,
            replace(base.rollup, min_independent_groups=2.5),
            base.breaking_mode,
            base.budget,
        )


def test_breaking_bar_below_normal_bar_is_rejected() -> None:
    base = cfg()
    bad = RollupConfig(
        margin=base.rollup.margin,
        min_independent_groups=3,
        min_independent_groups_breaking=2,
        min_high_tier_groups=1,
        strong_margin=base.rollup.strong_margin,
        strong_min_groups=base.rollup.strong_min_groups,
        moderate_margin=base.rollup.moderate_margin,
        moderate_min_groups=base.rollup.moderate_min_groups,
    )
    with pytest.raises(ValueError, match="min_independent_groups_breaking"):
        Config(base.tier_weights, base.recency, bad, base.breaking_mode, base.budget)


def test_build_verdict_records_versions_and_config_hash() -> None:
    weighted, candidate = run([ev("gov.example", P), ev("news-a.example", J)])
    final = apply_validation(
        candidate, validate(weighted, candidate, cfg(), FRESH_BUDGET)
    )
    verdict = build_verdict(
        final,
        cfg(),
        laya_version="laya-0.1",
        laya_checkpoint="ckpt-7",
        question_schema_version="q-v1",
        investigation_id="inv-42",
    )
    assert verdict.verdict is VerdictLabel.TRUE
    assert verdict.config_version == config_hash(cfg())
    assert (verdict.laya_version, verdict.investigation_id) == ("laya-0.1", "inv-42")


def test_build_verdict_refuses_a_verdict_outside_the_allowed_set() -> None:
    forged = VerdictCandidate(
        VerdictLabel.TRUE,
        Strength.STRONG,
        breaking_mode=False,
        allowed_verdicts=frozenset({VerdictLabel.UNCLEAR}),
    )
    with pytest.raises(ValueError, match="not in the allowed set"):
        build_verdict(
            forged,
            cfg(),
            laya_version="x",
            laya_checkpoint="y",
            question_schema_version="z",
            investigation_id="i",
        )
    with pytest.raises(ValueError, match="not in the allowed set"):
        build_verdict(
            VerdictCandidate(VerdictLabel.UNCLEAR, Strength.WEAK, breaking_mode=False),
            cfg(),
            laya_version="x",
            laya_checkpoint="y",
            question_schema_version="z",
            investigation_id="i",
        )


# --------------------------------------------------------------------------- #
# Config + purity
# --------------------------------------------------------------------------- #


def test_cfg_helper_mirrors_weights_toml_exactly() -> None:
    path = Path(__file__).resolve().parents[1] / "config" / "weights.toml"
    assert load_config(path) == cfg()


def test_config_hash_is_stable_and_sensitive_to_changes() -> None:
    base = cfg()
    tweaked = Config(
        tier_weights=base.tier_weights,
        recency=base.recency,
        rollup=RollupConfig(
            margin=0.35,
            min_independent_groups=base.rollup.min_independent_groups,
            min_independent_groups_breaking=base.rollup.min_independent_groups_breaking,
            min_high_tier_groups=base.rollup.min_high_tier_groups,
            strong_margin=base.rollup.strong_margin,
            strong_min_groups=base.rollup.strong_min_groups,
            moderate_margin=base.rollup.moderate_margin,
            moderate_min_groups=base.rollup.moderate_min_groups,
        ),
        breaking_mode=base.breaking_mode,
        budget=base.budget,
    )
    assert config_hash(base) == config_hash(cfg())
    assert config_hash(base) != config_hash(tweaked)


def test_weighting_and_validation_sources_contain_no_io_or_clock() -> None:
    """Invariant I8: the pure packages import no I/O library and never read a clock."""
    forbidden_modules = {
        "httpx",
        "aiogram",
        "sqlalchemy",
        "requests",
        "time",
        "socket",
        "os",
        "pathlib",
        "tomllib",
        "random",
        "subprocess",
        "urllib",
        "asyncio",
    }
    forbidden_calls = {"now", "utcnow", "today", "time", "monotonic", "open"}
    root = Path(__file__).resolve().parents[1] / "src" / "shayeban"
    sources = [*(root / "weighting").glob("*.py"), *(root / "validation").glob("*.py")]
    assert len(sources) >= 3

    for source in sources:
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[0] for alias in node.names}
                assert names.isdisjoint(forbidden_modules), f"{source.name}: {names}"
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                assert node.module.split(".")[0] not in forbidden_modules, (
                    f"{source.name}: {node.module}"
                )
            elif isinstance(node, ast.Call):
                func = node.func
                called = (
                    func.attr
                    if isinstance(func, ast.Attribute)
                    else getattr(func, "id", "")
                )
                assert called not in forbidden_calls, f"{source.name}: calls {called}"
