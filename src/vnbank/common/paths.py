"""Repository locations (CLAUDE.md, Repo layout). One place, so moving code never moves data."""

from __future__ import annotations

from pathlib import Path


def _find_repo() -> Path:
    for d in Path(__file__).resolve().parents:
        if (d / "pyproject.toml").is_file() and (d / "dbt").is_dir():
            return d
    raise RuntimeError("repository root not found above " + __file__)


REPO = _find_repo()
SNAPSHOTS = REPO / "data" / "snapshots"  # frozen research snapshots (git-ignored)
SEEDS = REPO / "dbt" / "seeds"


def paper_dir(paper: int) -> Path:
    return REPO / "research" / f"paper{paper}"


def runs_dir(paper: int) -> Path:
    return paper_dir(paper) / "runs"


def frozen_input(snapshot: str | None, name: str, fallback: Path) -> tuple[Path, str]:
    """A derived input (D-024 gate 1, P2-017): from the frozen snapshot when it holds the file,
    else the working copy (development snapshots predate the move). Returns (path, source)."""
    if snapshot:
        p = SNAPSHOTS / snapshot / name
        if p.exists():
            return p, f"snapshot:{snapshot}"
    return fallback / Path(name).name, f"working:{fallback.relative_to(REPO)}"
