"""Diagnostic (not pre-registered): extra shuffled-label controls for D-022, 2016 fold.

    uv run python scripts/diag_d022_shuffle.py <out.json>

Run 2026-11-25 (research/paper1/runs/RUNS.md: diag-D-022-shuffle). Fits nn_seq_ABCD and the
ABCDx logistic hazard with the 2016 fold's chosen parameters on training outcomes permuted
across rows (seeds 3..14) and reports Uno's C on the 2016 validation rows.
"""

import json
import sys

import numpy as np
import pandas as pd

from vnbank.research.survival.dev_decompose import (
    SPECS_D022,
    add_direction_interactions,
    add_sequences,
)
from vnbank.research.survival.evaluation.metrics import surv, uno_c
from vnbank.research.survival.models.zoo import make_model
from vnbank.research.survival.walkforward import DEV_END, TAU, split

FR = "research/paper1/runs/20261124T081754Z-features-b536ec69488162e0-k2"
SNAP = "data/snapshots/b536ec69488162e0"
D022 = "research/paper1/runs/20261124T211529Z-devdecompose-D-022"
COLS = ["ticker", "trade_date", "open_adj", "high_adj", "low_adj", "close_adj", "volume"]


def main(out_path: str) -> None:
    ds = pd.read_parquet(f"{FR}/dataset.parquet")
    ds = add_direction_interactions(ds[ds.trade_date <= DEV_END])
    px = pd.read_parquet(f"{SNAP}/prices_adjusted.parquet", columns=COLS)
    px["trade_date"] = pd.to_datetime(px.trade_date)
    ds = add_sequences(ds.reset_index(drop=True), px[px.trade_date <= DEV_END])
    sessions = np.sort(pd.to_datetime(pd.read_parquet(f"{SNAP}/sessions_hose.parquet").trade_date))
    train, val = split(ds, sessions, 2016, dev=True)
    y_train, y_val = surv(train.event, train.duration), surv(val.event, val.duration)
    chosen = json.load(open(f"{D022}/metrics.json"))["results"]["2016"]["chosen"]
    out = {}
    for spec, mname in (("nn_seq_ABCD", "nn"), ("ABCDx", "logit")):
        entry = SPECS_D022[spec]
        feats = entry[1] if isinstance(entry, tuple) else entry
        cs = []
        for k in range(3, 15):
            perm = np.random.default_rng(k).permutation(len(train))
            shuf = train.copy()
            shuf["duration"] = train.duration.to_numpy()[perm]
            shuf["event"] = train.event.to_numpy()[perm]
            model = make_model(mname, feats, **chosen[spec], seed=k).fit(shuf)
            s = model.survival(val, np.array([TAU]))
            cs.append(uno_c(y_train, y_val, 1 - s[:, 0], TAU))
            print(spec, k, round(cs[-1], 4), flush=True)
        out[spec] = {"values": np.round(cs, 4).tolist(), "mean": float(np.mean(cs)),
                     "sd": float(np.std(cs, ddof=1))}  # fmt: skip
        print(spec, out[spec], flush=True)
    json.dump(out, open(out_path, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
