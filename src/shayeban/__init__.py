"""SHAYEBAN - Telegram fact-checking bot (Task 13: pure weighting + validation core).

This package root is the ONLY place in Task 13 that touches the filesystem: it
offers :func:`load_config`, which reads ``config/weights.toml`` (spec §11) and
hands the parsed mapping to the pure :func:`config_from_mapping`. The
``weighting`` and ``validation`` packages never read files (invariant I8).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from shayeban.weighting.models import Config, config_from_mapping

__version__ = "0.1.0"

__all__ = ["Config", "__version__", "load_config"]


def load_config(path: str | Path) -> Config:
    """Read ``weights.toml`` from *path* and build the immutable :class:`Config`.

    All thresholds live in the TOML file (spec §11, ambiguity #7); this is the
    single I/O step, kept outside the pure core.
    """
    with Path(path).open("rb") as handle:
        data = tomllib.load(handle)
    return config_from_mapping(data)
