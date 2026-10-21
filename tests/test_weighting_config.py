"""Integration checks for the explicit file-loading boundary, outside the core."""

from dataclasses import asdict
from pathlib import Path

import pytest

from shayeban.settings.weights import load_weights


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
