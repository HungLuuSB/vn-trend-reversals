"""Build swing labels and survival rows from a frozen snapshot, and log the run.

    uv run python -m vnbank.research.swings.build --snapshot b536ec69488162e0 [--k 2 --k 1.5 --k 3]

Reads only data/snapshots/<id>/ (CLAUDE.md: models read only frozen snapshots). Writes
research/paper1/runs/<UTC timestamp>-labels-<id>/ with config.json (snapshot id, git commit,
k values, D-entries), reversals_k*.parquet, survival_k*.parquet and summary.json (descriptive
counts only: no model is fitted here).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from vnbank.common import paths
from vnbank.research.shared.config import load
from vnbank.research.swings.directional_change import label_series
from vnbank.research.swings.risk_set import MIN_HISTORY_DAYS, survival_rows

CFG = load(1)  # research/paper1/configs/main.yaml

REPO = paths.REPO
RUNS = paths.runs_dir(1)  # research/paper1/runs
STUDY_START, STUDY_END = pd.Timestamp("2012-01-03"), pd.Timestamp("2026-11-20")


def load(snapshot: str) -> dict[str, pd.DataFrame]:
    d = REPO / "data" / "snapshots" / snapshot
    if not (d / "manifest.json").exists():
        raise SystemExit(f"snapshot {snapshot} not found in {d.parent}")
    names = ["prices_adjusted", "prices_raw", "universe_daily", "sessions_hose", "price_limits"]
    return {n: pd.read_parquet(d / f"{n}.parquet") for n in names} | {
        "manifest": json.loads((d / "manifest.json").read_text())
    }


def label_stock(px: pd.DataFrame, sessions: pd.Series, universe: set, k: float):
    px = px.sort_values("trade_date").reset_index(drop=True)
    ticker = px["ticker"].iloc[0]
    lab = label_series(px["high_adj"].to_numpy(), px["low_adj"].to_numpy(),
                       px["close_adj"].to_numpy(), k=k)  # fmt: skip
    session_no = px["trade_date"].map(sessions).to_numpy()
    if np.isnan(session_no.astype("float64")).any():
        raise SystemExit(f"{ticker}: trading day outside the HOSE session calendar")
    in_uni = np.array([(ticker, d) in universe for d in px["trade_date"]])
    in_study = (px["trade_date"] >= STUDY_START) & (px["trade_date"] <= STUDY_END)
    end_index = int(np.flatnonzero(in_study.to_numpy()).max()) if in_study.any() else -1
    rows = survival_rows(lab, session_no.astype("int64"), in_uni & in_study.to_numpy(),
                         end_index, min_history=0)  # fmt: skip
    rows = rows.merge(px[["trade_date", "n_prior_days"]], left_on="index", right_index=True)
    # date of the event or censoring (needed to purge training rows whose label overlaps a
    # validation or test window)
    rows["end_date"] = px["trade_date"].to_numpy()[(rows["index"] + rows["duration"]).to_numpy()]
    rows = rows[rows["n_prior_days"] >= MIN_HISTORY_DAYS]  # D-009: point in time
    rows.insert(0, "ticker", ticker)
    rev = pd.DataFrame([r.__dict__ for r in lab.reversals])
    if not rev.empty:
        rev["confirm_date"] = px["trade_date"].iloc[rev["confirm_index"]].to_numpy()
        rev["extreme_date"] = px["trade_date"].iloc[rev["extreme_index"]].to_numpy()
        rev.insert(0, "ticker", ticker)
    return rows.drop(columns=["index"]), rev


def summarise(surv: pd.DataFrame, rev: pd.DataFrame) -> dict:
    by_reason = surv[surv.event == 0].censor_reason.value_counts().to_dict()
    return {
        "rows": int(len(surv)),
        "stocks": int(surv.ticker.nunique()),
        "event_rows": int(surv.event.sum()),
        "censored_rows": int((surv.event == 0).sum()),
        "censored_by_reason": {k: int(v) for k, v in by_reason.items()},
        "rows_up_share": float((surv.direction == 1).mean()),
        "reversals_in_study": int(
            ((rev.confirm_date >= STUDY_START) & (rev.confirm_date <= STUDY_END)).sum()
        ),  # fmt: skip
        "median_duration_at_entry_event_rows": float(
            surv[(surv.event == 1) & (surv.age_conf == 0)].duration.median()
        ),
        "median_swing_age_at_reversal": float(
            (surv[surv.event == 1].age + surv[surv.event == 1].duration)
            .groupby([surv.ticker, surv.age - surv.age_conf])
            .first()
            .median()
        ),
        "share_rows_reversal_within_5d": float(((surv.event == 1) & (surv.duration <= 5)).mean()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--k", type=float, action="append", help="threshold multiple(s)")
    args = parser.parse_args(argv)
    ks = args.k or [CFG["labels"]["k_main"], *CFG["labels"]["k_robustness"]]

    data = load(args.snapshot)
    px = data["prices_adjusted"].merge(
        data["prices_raw"][["ticker", "trade_date", "n_prior_days"]], on=["ticker", "trade_date"]
    )
    px["trade_date"] = pd.to_datetime(px["trade_date"])
    sessions = pd.Series(data["sessions_hose"]["session_no"].to_numpy(),
                         index=pd.to_datetime(data["sessions_hose"]["trade_date"]))  # fmt: skip
    uni = data["universe_daily"]
    universe = set(zip(uni.ticker, pd.to_datetime(uni.trade_date), strict=True))
    # trading days outside HOSE sessions (e.g. HNX/UPCoM-only days) cannot be on the calendar
    px = px[px["trade_date"].isin(sessions.index)]

    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                            text=True, check=True).stdout.strip()  # fmt: skip
    run_dir = RUNS / (f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-labels-{args.snapshot}")
    run_dir.mkdir(parents=True)
    config = {"snapshot_id": args.snapshot, "git_commit": commit, "k": ks,
              "decisions": ["D-001", "D-009", "D-011"], "min_history_days": MIN_HISTORY_DAYS,
              "created_at_utc": datetime.now(UTC).isoformat()}  # fmt: skip
    (run_dir / "config.json").write_text(json.dumps(config, indent=2))

    summary = {}
    for k in ks:
        surv_parts, rev_parts = [], []
        for _, g in px.groupby("ticker", sort=True):
            s, r = label_stock(g, sessions, universe, k)
            surv_parts.append(s)
            rev_parts.append(r)
        surv = pd.concat(surv_parts, ignore_index=True)
        rev = pd.concat([r for r in rev_parts if not r.empty], ignore_index=True)
        tag = f"k{k:g}".replace(".", "_")
        surv.to_parquet(run_dir / f"survival_{tag}.parquet", index=False)
        rev.to_parquet(run_dir / f"reversals_{tag}.parquet", index=False)
        summary[tag] = summarise(surv, rev)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({"run_dir": str(run_dir), **summary}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
