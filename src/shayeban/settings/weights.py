"""The file-reading boundary for the pure weighting engine."""

import tomllib
from pathlib import Path

from shayeban.weighting import TierWeights, WeightingConfig


def load_weights(path: Path) -> WeightingConfig:
    """Read initial thresholds explicitly, never at import time."""
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    tiers = TierWeights(**data["tiers"])
    return WeightingConfig(tiers=tiers, **data["weighting"])
