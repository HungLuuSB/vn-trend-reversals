"""Run metadata helpers (CLAUDE.md: every run logs its git commit)."""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def code_version() -> str:
    """HEAD commit, with "+dirty" if tracked files differ from it. Call at the start of a run."""

    def git(*a):
        return subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True,
                              check=True).stdout.strip()  # fmt: skip

    dirty = git("status", "--porcelain", "--untracked-files=no")
    return git("rev-parse", "HEAD") + ("+dirty" if dirty else "")
