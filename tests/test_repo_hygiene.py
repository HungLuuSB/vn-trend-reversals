"""Guards the 'never commit data or secrets' rule (CLAUDE.md, data rule 2).

Fails if any tracked file is a data file, a raw download, or an env file with secrets.
"""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

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


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, check=True, capture_output=True
    ).stdout.decode()
    return [Path(p) for p in out.split("\0") if p]


def test_no_data_files_tracked():
    bad = [p for p in tracked_files() if p.suffix.lower() in FORBIDDEN_SUFFIXES]
    assert not bad, f"data files must not be committed: {bad}"


def test_no_env_files_tracked():
    bad = [
        p
        for p in tracked_files()
        if (p.name == ".env" or p.name.startswith(".env.")) and p.name not in ALLOWED_ENV_FILES
    ]
    assert not bad, f"env files must not be committed: {bad}"


def test_gitignore_blocks_env_and_data():
    ignored = subprocess.run(
        ["git", "check-ignore", "--no-index", ".env", "x.parquet", "x.csv", "raw/a.json"],
        cwd=REPO,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert set(ignored) == {".env", "x.parquet", "x.csv", "raw/a.json"}
