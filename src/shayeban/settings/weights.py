"""Explicit shared evidence-policy loading; runtime accounting stays elsewhere."""

import hashlib
import json
import tomllib
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any, get_type_hints

from shayeban.weighting import TierWeights, WeightingConfig


@dataclass(frozen=True)
class BudgetConfig:
    """Limits for the harness, with explicit total-versus-per-query units."""

    max_search_queries: int
    max_fetches_per_query: int

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{field.name} must be a positive integer")


@dataclass(frozen=True)
class BreakingConfig:
    """Initial harness detection/cache/scheduling policy, not scoring logic."""

    high_velocity_15m: int
    low_velocity_1h: int
    normal_cache_ttl_minutes: int
    breaking_cache_ttl_minutes: int
    normal_recheck_interval_minutes: int
    breaking_recheck_interval_minutes: int

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{field.name} must be a positive integer")
        if self.low_velocity_1h >= self.high_velocity_15m:
            raise ValueError("low_velocity_1h must be below high_velocity_15m")
        if self.breaking_cache_ttl_minutes >= self.normal_cache_ttl_minutes:
            raise ValueError("breaking cache TTL must be shorter than normal TTL")
        if (
            self.breaking_recheck_interval_minutes
            >= self.normal_recheck_interval_minutes
        ):
            raise ValueError("breaking re-check must be more frequent than normal")


@dataclass(frozen=True)
class EvidenceSettings:
    """Complete parsed policy; pass only each subsystem's own config to it."""

    weighting: WeightingConfig
    budget: BudgetConfig
    breaking: BreakingConfig

    @property
    def config_version(self) -> str:
        """Stable effective-policy identity, ready for future provenance wiring."""
        canonical = json.dumps(
            asdict(self), sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _section[Config: (TierWeights, WeightingConfig, BudgetConfig, BreakingConfig)](
    config_type: type[Config],
    data: dict[str, Any],
    name: str,
    **injected: Any,
) -> Config:
    """Reject omitted/unknown/mistyped settings instead of silently ignoring them."""
    if name not in data:
        raise ValueError(f"missing [{name}] section")
    table = data[name]
    if not isinstance(table, dict):
        raise TypeError(f"[{name}] must be a table")
    required = {
        name: kind
        for name, kind in get_type_hints(config_type).items()
        if name not in injected
    }
    if missing := required.keys() - table.keys():
        raise ValueError(f"[{name}] missing settings: {', '.join(sorted(missing))}")
    if unknown := table.keys() - required.keys():
        raise ValueError(f"[{name}] unknown settings: {', '.join(sorted(unknown))}")
    values = dict(table)
    for key, kind in required.items():
        value = values[key]
        if kind is int and type(value) is not int:
            raise ValueError(f"[{name}].{key} must be an integer")
        if kind is float:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError(f"[{name}].{key} must be numeric")
            values[key] = float(value)
    try:
        return config_type(**values, **injected)
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid [{name}]: {error}") from error


def load_evidence_settings(path: Path) -> EvidenceSettings:
    """Load and validate the entire shared file, never implicitly at import time."""
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    expected = {"tiers", "weighting", "budget", "breaking"}
    if unknown := data.keys() - expected:
        raise ValueError(
            f"unknown configuration sections: {', '.join(sorted(unknown))}"
        )
    tiers = _section(TierWeights, data, "tiers")
    return EvidenceSettings(
        weighting=_section(WeightingConfig, data, "weighting", tiers=tiers),
        budget=_section(BudgetConfig, data, "budget"),
        breaking=_section(BreakingConfig, data, "breaking"),
    )


def load_weights(path: Path) -> WeightingConfig:
    """Compatibility view of scoring config, after validating all shared policy."""
    return load_evidence_settings(path).weighting
