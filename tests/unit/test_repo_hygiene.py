"""Guards the 'never commit data or secrets' rule (CLAUDE.md, data rule 2).

Fails if any tracked file is a data file, a raw download, or an env file with secrets.
"""

import subprocess
from pathlib import Path

from vnbank.common import paths

REPO = paths.REPO

FORBIDDEN_SUFFIXES = {
    ".parquet",
    ".csv",
    ".tsv",
    ".feather",
    ".arrow",
    ".xlsx",
    ".xls",
    ".pdf",
    ".zip",
    ".gz",
}
ALLOWED_ENV_FILES = {".env.example"}
# Curated reference seeds (sourced, hand-checked, small) are code, not data (CLAUDE.md rule 2).
ALLOWED_DATA_DIRS = {Path("dbt/seeds")}
MAX_SEED_BYTES = 500_000


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, check=True, capture_output=True
    ).stdout.decode()
    return [Path(p) for p in out.split("\0") if p]


def test_no_data_files_tracked():
    bad = [
        p
        for p in tracked_files()
        if p.suffix.lower() in FORBIDDEN_SUFFIXES
        and not (p.parent in ALLOWED_DATA_DIRS and p.suffix.lower() == ".csv")
    ]
    assert not bad, f"data files must not be committed: {bad}"


def test_seed_csvs_stay_small():
    seeds = [p for p in tracked_files() if p.parent in ALLOWED_DATA_DIRS and p.suffix == ".csv"]
    big = [p for p in seeds if (REPO / p).stat().st_size > MAX_SEED_BYTES]
    assert not big, f"seed files too large to be reference data: {big}"


def test_no_env_files_tracked():
    bad = [
        p
        for p in tracked_files()
        if (p.name == ".env" or p.name.startswith(".env.")) and p.name not in ALLOWED_ENV_FILES
    ]
    assert not bad, f"env files must not be committed: {bad}"


def test_gitignore_blocks_env_and_data():
    ignored = subprocess.run(
        [
            "git",
            "check-ignore",
            "--no-index",
            ".env",
            "x.parquet",
            "x.csv",
            "raw/a.json",
            "dbt/seeds/a.csv",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert set(ignored) == {".env", "x.parquet", "x.csv", "raw/a.json"}
