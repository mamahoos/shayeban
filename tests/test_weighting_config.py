"""Integration checks for the explicit file-loading boundary, outside the core."""

from dataclasses import asdict
from pathlib import Path

import pytest

from shayeban.settings.weights import load_evidence_settings, load_weights

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config/weights.toml"


def test_committed_weights_config_loads() -> None:
    config = load_weights(Path(__file__).resolve().parents[1] / "config/weights.toml")
    assert config.min_groups == 2
    assert config.breaking_min_groups >= config.min_groups
    assert config.tiers.unknown == 0


def test_config_loading_is_cwd_independent(tmp_path: Path) -> None:
    original = Path(__file__).resolve().parents[1] / "config/weights.toml"
    copied = tmp_path / "weights.toml"
    copied.write_bytes(original.read_bytes())
    assert asdict(load_weights(copied)) == asdict(load_weights(original))


def test_invalid_toml_thresholds_fail_at_boundary(tmp_path: Path) -> None:
    original = Path(__file__).resolve().parents[1] / "config/weights.toml"
    invalid = tmp_path / "weights.toml"
    invalid.write_text(
        original.read_text(encoding="utf-8").replace(
            "min_groups = 2", "min_groups = 0"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="positive integers"):
        load_weights(invalid)


def test_shared_policy_includes_documented_budget_and_breaking_defaults() -> None:
    settings = load_evidence_settings(CONFIG_PATH)
    assert settings.weighting == load_weights(CONFIG_PATH)
    assert settings.budget.max_search_queries == 4
    assert settings.budget.max_fetches_per_query == 5
    assert settings.breaking.high_velocity_15m == 10
    assert settings.breaking.low_velocity_1h == 5
    assert settings.breaking.normal_cache_ttl_minutes == 24 * 60
    assert 15 <= settings.breaking.breaking_cache_ttl_minutes <= 30
    assert 1 <= settings.breaking.breaking_recheck_interval_minutes <= 2


@pytest.mark.parametrize("section", ["tiers", "weighting", "budget", "breaking"])
def test_missing_sections_are_rejected_instead_of_silently_ignored(
    tmp_path: Path, section: str
) -> None:
    text = CONFIG_PATH.read_text(encoding="utf-8")
    before, after = text.split(f"[{section}]", 1)
    following_section = after.find("\n[")
    text = before + (after[following_section + 1 :] if following_section >= 0 else "")
    incomplete = tmp_path / "weights.toml"
    incomplete.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=f"missing \\[{section}\\]"):
        load_evidence_settings(incomplete)
    # Existing callers cannot accidentally bypass full-file validation.
    with pytest.raises(ValueError):
        load_weights(incomplete)


@pytest.mark.parametrize(
    ("old", "new", "reason"),
    [
        ("max_search_queries = 4", "max_search_queries = 0", "positive integer"),
        ("max_fetches_per_query = 5", "max_fetches_per_query = -1", "positive integer"),
        ("max_fetches_per_query = 5", "max_fetches_per_query = 5.0", "integer"),
        ("max_search_queries = 4", "max_search_queries = true", "integer"),
        ("high_velocity_15m = 10", "high_velocity_15m = 0", "positive integer"),
        ("low_velocity_1h = 5", "low_velocity_1h = 10", "below"),
        (
            "breaking_cache_ttl_minutes = 15",
            "breaking_cache_ttl_minutes = 1440",
            "shorter",
        ),
        (
            "breaking_recheck_interval_minutes = 1",
            "breaking_recheck_interval_minutes = 240",
            "frequent",
        ),
        ("fresh_factor = 1.0", "fresh_factor = true", "numeric"),
        ("stale_factor = 0.3", "stale_factor = nan", "finite"),
        ("max_search_queries = 4", "max_search_query = 4", "missing settings"),
    ],
)
def test_invalid_shared_policy_fails_with_a_section_error(
    tmp_path: Path, old: str, new: str, reason: str
) -> None:
    invalid = tmp_path / "weights.toml"
    invalid.write_text(
        CONFIG_PATH.read_text(encoding="utf-8").replace(old, new), encoding="utf-8"
    )
    with pytest.raises(ValueError, match=reason):
        load_evidence_settings(invalid)


@pytest.mark.parametrize(
    "extra", ["\n[unexpected]\nvalue = 1\n", "\nunknown_key = 1\n"]
)
def test_unknown_sections_or_keys_fail(tmp_path: Path, extra: str) -> None:
    invalid = tmp_path / "weights.toml"
    invalid.write_text(
        CONFIG_PATH.read_text(encoding="utf-8") + extra, encoding="utf-8"
    )
    with pytest.raises(ValueError, match="unknown"):
        load_evidence_settings(invalid)


def test_config_version_is_stable_for_formatting_and_sensitive_to_all_sections(
    tmp_path: Path,
) -> None:
    original = CONFIG_PATH.read_text(encoding="utf-8")
    baseline = load_evidence_settings(CONFIG_PATH).config_version
    assert len(baseline) == 64
    changed = tmp_path / "weights.toml"
    changed.write_text("# formatting change\n" + original + "\n", encoding="utf-8")
    assert load_evidence_settings(changed).config_version == baseline
    # Numeric spelling does not change the effective typed setting.
    changed.write_text(
        original.replace("fresh_factor = 1.0", "fresh_factor = 1"), encoding="utf-8"
    )
    assert load_evidence_settings(changed).config_version == baseline
    for old, new in [
        ("primary = 1.0", "primary = 1.1"),
        ("margin = 0.3", "margin = 0.35"),
        ("max_search_queries = 4", "max_search_queries = 3"),
        ("high_velocity_15m = 10", "high_velocity_15m = 11"),
    ]:
        changed.write_text(original.replace(old, new), encoding="utf-8")
        assert load_evidence_settings(changed).config_version != baseline
