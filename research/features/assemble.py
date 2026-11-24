"""Assemble the modelling dataset: survival rows + feature blocks A-D, from one snapshot.

    uv run python -m research.features.assemble --snapshot <id> --labels-run <run dir> [--k 2]

Each row (stock, t) gets
  A  swing state after the close of t (labels recomputed from the snapshot, same k)
  B  stock technicals after the close of t
  C  local market from local_market_daily of the decision session d (= the next HOSE session
     after t; that row describes session t)
  D  global features of the decision session d (values public before 09:00 on d)
plus targets (duration, event, end_date), universe flags and days_to_dev_end (for censoring
development evaluations at 2016-12-31; D-012). The look-ahead rule is re-checked here.
Foreign flows are kept but excluded from the main feature list (D-012).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from research.features.stock import block_a, block_b
from research.labels.directional_change import label_series

REPO = Path(__file__).resolve().parents[2]
DEV_END = pd.Timestamp("2016-12-31")

FEATURES_A = ["swing_dir", "swing_age", "log_age", "swing_age_conf", "swing_move", "swing_dist",
              "theta"]  # fmt: skip
FEATURES_B = ["ret_1", "ret_5", "ret_20", "atr_pct", "rsi_14", "vol_rel_20", "limit_up_hits_5",
              "limit_down_hits_5", "limit_known_5", "close_at_limit"]  # fmt: skip
FEATURES_C = ["vnindex_ret", "vn30_ret", "advance_share", "matched_value_rel_20",
              "idx_swing_dir", "idx_swing_age", "idx_swing_dist"]  # fmt: skip
FEATURES_C_ROBUST = ["foreign_net_share"]  # D-012: robustness only
FEATURES_D = ["spx_ret", "nasdaq_ret", "vix_chg", "vix_level", "ust10_chg", "dxy_ret", "gold_ret",
              "brent_ret", "hsi_ret", "sse_ret", "usdvnd_ret", "usdcny_ret", "gpr_level",
              "gpr_chg"]  # fmt: skip
BLOCKS = {"A": FEATURES_A, "B": FEATURES_B, "C": FEATURES_C, "D": FEATURES_D}


def stock_blocks(px: pd.DataFrame, k: float) -> pd.DataFrame:
    px = px.sort_values("trade_date").reset_index(drop=True)
    lab = label_series(px.high_adj, px.low_adj, px.close_adj, k=k)
    out = pd.concat([px[["ticker", "trade_date"]], block_a(px.close_adj.to_numpy(), lab),
                     block_b(px)], axis=1)  # fmt: skip
    out["log_age"] = np.log1p(out["swing_age"])
    # trading days of this stock from t to its last trading day <= DEV_END (dev censoring)
    idx = np.arange(len(px))
    last_dev = np.flatnonzero((px.trade_date <= DEV_END).to_numpy())
    out["days_to_dev_end"] = (last_dev.max() - idx) if len(last_dev) else -1
    return out


def index_blocks(local: pd.DataFrame, k: float) -> pd.DataFrame:
    """VN-Index swing state at each session t, from closes known after t (H = L = close)."""
    s = local.dropna(subset=["source_session", "vnindex_close"]).sort_values("source_session")
    c = s.vnindex_close.to_numpy()
    lab = label_series(c, c, c, k=k)
    a = block_a(c, lab)
    return pd.DataFrame({
        "trade_date": pd.to_datetime(s.source_session).to_numpy(),
        "idx_swing_dir": a.swing_dir.to_numpy(),
        "idx_swing_age": a.swing_age.to_numpy(),
        "idx_swing_dist": a.swing_dist.to_numpy(),
    })  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--labels-run", required=True, help="research/runs/<...-labels-...>")
    parser.add_argument("--k", type=float, default=2.0)
    args = parser.parse_args(argv)

    snap = REPO / "research" / "snapshots" / args.snapshot
    read = lambda n: pd.read_parquet(snap / f"{n}.parquet")  # noqa: E731
    tag = f"k{args.k:g}".replace(".", "_")
    rows = pd.read_parquet(Path(args.labels_run) / f"survival_{tag}.parquet")
    labels_cfg = json.loads((Path(args.labels_run) / "config.json").read_text())
    if labels_cfg["snapshot_id"] != args.snapshot:
        raise SystemExit("labels run was built from a different snapshot")

    adj, lim = read("prices_adjusted"), read("price_limits")
    px = adj.merge(lim[["ticker", "trade_date", "close_at_ceiling", "close_at_floor",
                        "limit_status"]], on=["ticker", "trade_date"], how="left")  # fmt: skip
    px["trade_date"] = pd.to_datetime(px.trade_date)
    sessions = pd.to_datetime(read("sessions_hose").trade_date).sort_values().to_numpy()
    px = px[px.trade_date.isin(sessions)]
    stock = pd.concat([stock_blocks(g, args.k) for _, g in px.groupby("ticker", sort=True)])

    local = read("local_market")
    glob = read("global_features")
    for df in (local, glob):
        df["trade_date"] = pd.to_datetime(df.trade_date)
    # look-ahead re-check (dbt tests the same in the warehouse)
    assert (
        local.available_at_utc.dropna() < local.decision_time_utc[local.available_at_utc.notna()]
    ).all()
    assert (glob.available_at_max_utc < glob.decision_time_utc).all()
    local = local.sort_values("trade_date")
    local["matched_value_rel_20"] = local.hose_matched_value_bn / (
        local.hose_matched_value_bn.rolling(20, min_periods=20).mean()
    )
    glob = glob.copy()
    glob.loc[glob.gold_roll_window.astype(bool), "gold_ret"] = np.nan  # D-012

    rows["trade_date"] = pd.to_datetime(rows.trade_date)
    rows["end_date"] = pd.to_datetime(rows.end_date)
    pos = np.searchsorted(sessions, rows.trade_date.to_numpy(), side="right")
    rows["decision_date"] = pd.NaT
    ok = pos < len(sessions)
    rows.loc[ok, "decision_date"] = sessions[pos[ok]]

    ds = rows.merge(stock, on=["ticker", "trade_date"], how="left", suffixes=("", "_feat"))
    ds = ds.merge(index_blocks(local, args.k), on="trade_date", how="left")
    ds = ds.merge(local[["trade_date", "vnindex_ret", "vn30_ret", "advance_share",
                         "matched_value_rel_20", "foreign_net_share"]]
                  .rename(columns={"trade_date": "decision_date"}), on="decision_date",
                  how="left")  # fmt: skip
    ds = ds.merge(glob[["trade_date", *FEATURES_D]].rename(columns={"trade_date": "decision_date"}),
                  on="decision_date", how="left")  # fmt: skip
    uni = read("universe_daily")
    uni["trade_date"] = pd.to_datetime(uni.trade_date)
    ds = ds.merge(uni[["ticker", "trade_date", "in_vn30", "is_bank", "bank_on_upcom"]],
                  on=["ticker", "trade_date"], how="left")  # fmt: skip
    # the labeller's swing state and the recomputed one must agree (same snapshot, same k)
    assert (ds.direction == ds.swing_dir).all() and (ds.age == ds.swing_age).all()

    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True,
                            text=True, check=True).stdout.strip()  # fmt: skip
    run = (
        REPO
        / "research"
        / "runs"
        / (f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-features-{args.snapshot}-{tag}")
    )
    run.mkdir(parents=True)
    ds.to_parquet(run / "dataset.parquet", index=False)
    cfg = {"snapshot_id": args.snapshot, "labels_run": Path(args.labels_run).name, "k": args.k,
           "git_commit": commit, "blocks": BLOCKS, "robustness_only": FEATURES_C_ROBUST,
           "rows": len(ds), "decisions": ["D-009", "D-011", "D-012"]}  # fmt: skip
    (run / "config.json").write_text(json.dumps(cfg, indent=2))
    missing = ds[[c for b in BLOCKS.values() for c in b]].isna().mean().round(4)
    print(json.dumps({"run_dir": str(run), "rows": len(ds),
                      "missing_share": missing[missing > 0].to_dict()}, indent=2))  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
