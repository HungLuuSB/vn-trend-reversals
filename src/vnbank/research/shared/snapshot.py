"""Freeze a research snapshot (CLAUDE.md: models read only frozen snapshots).

    uv run python -m vnbank.research.shared.snapshot [--label dev-v1]

Exports the research tables from ClickHouse to Parquet under data/snapshots/<id>/, writes
a manifest (git commit, pinned raw archives, seed hashes, SQL, row counts), derives the
snapshot id from the content, copies everything to the raw layer under snapshots/<id>/, and
appends a row to research/snapshots.md. Refuses to run if the last dbt build had failures,
the working tree is dirty, or any row is dated after the study end (D-001).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq

from vnbank.common import paths
from vnbank.common.clickhouse import client_from_env
from vnbank.common.env import load_dotenv
from vnbank.common.raw_store import S3RawStore
from vnbank.research.shared.config import load

CFG = load(1)  # research/paper1/configs/main.yaml

REPO = paths.REPO
SNAP_DIR = REPO / "data" / "snapshots"
REGISTRY = REPO / "research" / "snapshots.md"
STUDY_START, STUDY_END = CFG["study"]["start"], CFG["study"]["end"]  # D-001, P2-001
WARMUP_START = CFG["study"]["warmup_start"]  # D-001: initialises trailing quantities only

UNIVERSE_TICKERS = "(SELECT DISTINCT ticker FROM research_universe_daily)"

# name -> (SQL, date column checked against STUDY_END or None). Every query has a total order.
TABLES: dict[str, tuple[str, str | None]] = {
    "universe_daily": (
        "SELECT * FROM research_universe_daily ORDER BY trade_date, ticker",
        "trade_date",
    ),
    "prices_raw": (
        f"""SELECT * FROM (
              SELECT *, row_number() OVER (PARTITION BY ticker ORDER BY trade_date) - 1
                        AS n_prior_days
              FROM prices_daily_raw WHERE ticker IN {UNIVERSE_TICKERS})
            WHERE trade_date BETWEEN '{WARMUP_START}' AND '{STUDY_END}'
            ORDER BY ticker, trade_date""",
        "trade_date",
    ),
    "prices_adjusted": (
        f"""SELECT * FROM prices_daily_adjusted WHERE ticker IN {UNIVERSE_TICKERS}
              AND trade_date BETWEEN '{WARMUP_START}' AND '{STUDY_END}'
            ORDER BY ticker, trade_date""",
        "trade_date",
    ),
    "price_limits": (
        f"""SELECT * FROM prices_daily_limits WHERE ticker IN {UNIVERSE_TICKERS}
              AND trade_date BETWEEN '{WARMUP_START}' AND '{STUDY_END}'
            ORDER BY ticker, trade_date""",
        "trade_date",
    ),
    "corporate_actions": (
        f"""SELECT * FROM int_corporate_actions_final WHERE ticker IN {UNIVERSE_TICKERS}
              AND ex_date <= '{STUDY_END}' ORDER BY ticker, ex_date""",
        "ex_date",
    ),
    "sessions_hose": (
        f"""SELECT * FROM int_trading_sessions WHERE exchange = 'HSX'
              AND trade_date BETWEEN '{WARMUP_START}' AND '{STUDY_END}' ORDER BY trade_date""",
        "trade_date",
    ),
    "vn30_membership": ("SELECT * FROM dim_vn30_membership ORDER BY ticker, valid_from", None),
    "bank_spells": ("SELECT * FROM bank_spells ORDER BY ticker, first_trade_date", None),
    "global_features": (
        f"""SELECT * FROM global_features_daily
            WHERE trade_date BETWEEN '{WARMUP_START}' AND '{STUDY_END}' ORDER BY trade_date""",
        "trade_date",
    ),
    "local_market": (
        f"""SELECT * FROM local_market_daily
            WHERE trade_date BETWEEN '{WARMUP_START}' AND '{STUDY_END}' ORDER BY trade_date""",
        "trade_date",
    ),
}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, check=True, capture_output=True,
                          text=True).stdout.strip()  # fmt: skip


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_dbt_clean() -> None:
    rr = REPO / "dbt" / "target" / "run_results.json"
    if not rr.exists():
        raise SystemExit("no dbt run_results.json: run `dbt build` first")
    results = json.loads(rr.read_text())["results"]
    bad = [r["unique_id"] for r in results if r["status"] not in ("success", "pass")]
    if bad:
        raise SystemExit(f"last dbt run had failures: {bad[:5]}")


def snapshot_id(files: dict[str, str], manifest_core: dict) -> str:
    h = hashlib.sha256()
    for name in sorted(files):
        h.update(f"{name}\t{files[name]}\n".encode())
    h.update(json.dumps(manifest_core, sort_keys=True).encode())
    return h.hexdigest()[:16]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", default="dev", help="short label for the registry")
    parser.add_argument("--allow-dirty", action="store_true", help="development use only")
    args = parser.parse_args(argv)

    check_dbt_clean()
    dirty = git("status", "--porcelain")
    if dirty and not args.allow_dirty:
        raise SystemExit("working tree has uncommitted changes; commit first")

    client = client_from_env()
    staging = SNAP_DIR / f"_staging_{datetime.now(UTC):%Y%m%dT%H%M%S}"
    staging.mkdir(parents=True)
    files, counts = {}, {}
    for name, (sql, date_col) in TABLES.items():
        table = client.query_arrow(sql)
        if date_col is not None and table.num_rows:
            latest = max(v for v in table.column(date_col).to_pylist() if v is not None)
            if latest > STUDY_END:
                raise SystemExit(f"{name}: row dated {latest} after the study end {STUDY_END}")
        path = staging / f"{name}.parquet"
        pq.write_table(table, path, compression="zstd")
        files[f"{name}.parquet"] = sha256_file(path)
        counts[name] = table.num_rows

    dbt_vars = (REPO / "dbt" / "dbt_project.yml").read_text()
    seeds = {p.name: sha256_file(p) for p in sorted((REPO / "dbt" / "seeds").glob("*.csv"))}
    core = {
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty": bool(dirty),
        "study_start": str(STUDY_START),
        "study_end": str(STUDY_END),
        "warmup_start": str(WARMUP_START),
        "dbt_project_yml_sha256": hashlib.sha256(dbt_vars.encode()).hexdigest(),
        "seed_sha256": seeds,
        "sql": {k: " ".join(v[0].split()) for k, v in TABLES.items()},
        "row_counts": counts,
        "files_sha256": files,
    }
    sid = snapshot_id(files, core)
    manifest = {"snapshot_id": sid, "label": args.label,
                "created_at_utc": datetime.now(UTC).isoformat(), **core}  # fmt: skip
    (staging / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))

    final = SNAP_DIR / sid
    if final.exists():
        raise SystemExit(f"snapshot {sid} already exists (identical content)")
    staging.rename(final)

    load_dotenv(["S3_"])
    raw = S3RawStore.from_env()
    for p in sorted(final.iterdir()):
        raw.put_immutable(f"snapshots/{sid}/{p.name}", p.read_bytes(),
                          {"snapshot_id": sid, "label": args.label})  # fmt: skip

    with open(REGISTRY, "a", encoding="utf-8") as fh:
        rows = ", ".join(f"{k} {v:,}" for k, v in counts.items())
        today = datetime.now(UTC).date()
        commit = core["git_commit"][:10] + (" (dirty)" if dirty else "")
        fh.write(f"| `{sid}` | {today} | {args.label} | `{commit}` | {rows} |\n")
    print(json.dumps({"snapshot_id": sid, "dir": str(final), "rows": counts}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
