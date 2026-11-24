"""Paper design configs (CLAUDE.md: "the design lives in research/paperN/configs/main.yaml")."""

from __future__ import annotations

from functools import cache
from itertools import product
from typing import Any

import yaml

from vnbank.common import paths


@cache
def load(paper: int, name: str = "main") -> dict[str, Any]:
    with open(paths.paper_dir(paper) / "configs" / f"{name}.yaml") as f:
        return yaml.safe_load(f)


def grid(spec: dict[str, list]) -> list[dict]:
    """{"C": [a, b], "l1_ratio": [x]} -> [{"C": a, "l1_ratio": x}, {"C": b, "l1_ratio": x}]."""
    keys = list(spec)
    return [dict(zip(keys, vals, strict=True)) for vals in product(*(spec[k] for k in keys))]
