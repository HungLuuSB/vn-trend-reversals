"""Load settings from the git-ignored ``.env`` file without ever printing them."""

from __future__ import annotations

import os
from collections.abc import Iterable


def load_dotenv(prefixes: Iterable[str], path: str = ".env") -> None:
    """Copy ``KEY=value`` lines whose key starts with one of ``prefixes`` into ``os.environ``.

    Variables already set in the environment win. Only the listed prefixes are read, so source
    API keys stored in the same file are never loaded by code that does not need them.
    """
    prefixes = tuple(prefixes)
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                key, sep, value = line.strip().partition("=")
                if sep and key.startswith(prefixes) and key not in os.environ:
                    os.environ[key] = value.strip().strip('"')
    except FileNotFoundError:
        pass
