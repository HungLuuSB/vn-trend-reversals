"""RQ4 / H4 (exploratory): did sensitivity to global shocks rise after the FTSE upgrade
announcement? FINAL_RUN_PROTOCOL.md section 5a (D-026).

    uv run python -m vnbank.research.survival.final.rq4 --features-run <dir> \
        --final --i-confirm-final-run

Full-sample landmark logistic hazard on ``ABCDx`` plus ``post`` (1 from the announcement,
seed market_classification_events) and ``post`` x each H2 channel and its direction term (10
terms). Ridge C = 100 replaces the tuned hyperparameters, only so the fit converges (D-026
clarification 2); joint Wald test of the 10 interactions (chi-squared, 10 df) with two-way
(date x ticker) clustered sandwich errors, date-only errors reported alongside. Placebos: the
same statistic with a placebo announcement on 7 October of 2013-2023, each sample ending 13
months later (labels censored there) and before the real announcement. H4 is supported only if
p < 0.05 and the real statistic exceeds every placebo.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sst
from sklearn.linear_model import LogisticRegression

from vnbank.common import paths
from vnbank.research.shared.config import load
from vnbank.research.shared.run_meta import code_version
from vnbank.research.survival.features.assemble import BLOCKS
from vnbank.research.survival.final.specs import ABCDx
from vnbank.research.survival.models.hazard import expand
from vnbank.research.survival.models.zoo import FIT_CAP

CFG = load(1)
CHANNELS = ["spx_ret", "nasdaq_ret", "vix_chg", "ust10_chg", "dxy_ret"]
POST_TERMS = [*CHANNELS, *(f"{c}_xdir" for c in CHANNELS)]
RIDGE_C = 100.0
MAX_STEP = CFG["evaluation"]["max_step"]
PLACEBO_YEARS = range(2013, 2024)
WINDOW = pd.DateOffset(months=13)


def censor_at(ds: pd.DataFrame, sessions: np.ndarray, end: pd.Timestamp) -> pd.DataFrame:
    """Rows up to `end`; labels reaching past it are censored at the last session <= end."""
    d = ds[ds.trade_date <= end].copy()
    k = np.searchsorted(sessions, end.to_datetime64(), side="right") - 1
    late = (d.end_date > end).to_numpy()
    left = k - np.searchsorted(sessions, d.trade_date.to_numpy())
    d.loc[late, "event"] = 0
    d.loc[late, "duration"] = np.minimum(d.duration.to_numpy(), left)[late]
    return d[d.duration > 0]


def design(d: pd.DataFrame, post_date: pd.Timestamp):
    """Landmark rows (D-013) with standardised ABCDx, post, post x POST_TERMS, step dummies."""
    x = d[ABCDx].to_numpy(dtype="float64")
    med = np.nanmedian(x, axis=0)
    x = np.where(np.isnan(x), med, x)
    sd = x.std(axis=0)
    x = (x - x.mean(axis=0)) / np.where(sd > 0, sd, 1)
    post = (d.trade_date >= post_date).to_numpy(float)
    idx = [ABCDx.index(t) for t in POST_TERMS]
    inter = x[:, idx] * post[:, None]
    base = np.hstack([x, post[:, None], inter])
    dur = np.minimum(d.duration.to_numpy(), FIT_CAP)
    ev = np.where(d.duration.to_numpy() > FIT_CAP, 0, d.event.to_numpy())
    rows, steps, y = expand(dur, ev, MAX_STEP)
    dummies = (steps[:, None] == np.arange(1, MAX_STEP + 1)[None, :]).astype(float)
    X = np.hstack([base[rows], dummies])
    groups = d.trade_date.to_numpy()[rows]
    tickers = d.ticker.to_numpy()[rows]
    post_cols = np.arange(x.shape[1] + 1, x.shape[1] + 1 + len(POST_TERMS))
    return X, y, groups, post_cols, tickers


def _meat(X, resid, groups) -> np.ndarray:
    _, g = np.unique(groups, return_inverse=True)
    s = np.zeros((g.max() + 1, X.shape[1]))
    np.add.at(s, g, X * resid[:, None])
    return s.T @ s


def _psd(V: np.ndarray) -> np.ndarray:
    """Cameron, Gelbach and Miller (2011): clip negative eigenvalues of a two-way variance."""
    w, U = np.linalg.eigh((V + V.T) / 2)
    return (U * np.clip(w, 0, None)) @ U.T


def _test(b, V, cols) -> dict:
    bc, Vc = b[cols], _psd(V[np.ix_(cols, cols)])
    stat = float(bc @ np.linalg.pinv(Vc) @ bc)
    return {"wald": stat, "df": len(cols), "p": float(sst.chi2.sf(stat, len(cols))),
            "se": dict(zip(POST_TERMS, np.round(np.sqrt(np.abs(np.diag(Vc))), 6).tolist(),
                           strict=True))}  # fmt: skip


def wald(X, y, groups, cols, tickers=None) -> dict:
    """Penalised fit (L2, C = RIDGE_C, no intercept: the step dummies span it) and sandwich
    covariances V = H^-1 B H^-1 clustered by date, and two-way by date and ticker (Cameron,
    Gelbach and Miller 2011): B = B_date + B_ticker - B_date x ticker, made positive
    semi-definite. Overlapping landmark rows of one swing share a ticker, so the two-way errors
    also cover that serial dependence. The decision uses the larger of the two p-values
    (D-026 clarification 2)."""
    m = LogisticRegression(C=RIDGE_C, l1_ratio=0.0, fit_intercept=False, max_iter=5000)
    m.fit(X, y)
    b = m.coef_[0]
    p = 1 / (1 + np.exp(-(X @ b)))
    Hm = (X * (p * (1 - p))[:, None]).T @ X + np.eye(X.shape[1]) / RIDGE_C
    Hi = np.linalg.inv(Hm)
    r = y - p
    out = {"coef": dict(zip(POST_TERMS, np.round(b[cols], 6).tolist(), strict=True)),
           "clusters_date": int(len(np.unique(groups)))}  # fmt: skip
    out["date"] = _test(b, Hi @ _meat(X, r, groups) @ Hi, cols)
    if tickers is not None:
        both = pd.factorize(pd.MultiIndex.from_arrays([groups, tickers]))[0]
        B = _meat(X, r, groups) + _meat(X, r, tickers) - _meat(X, r, both)
        out["two_way"] = _test(b, Hi @ B @ Hi, cols)
    # decision: the more conservative of the two (larger p), D-026 clarification 2
    main = max((out[k] for k in ("date", "two_way") if k in out), key=lambda t: t["p"])
    out.update({"wald": main["wald"], "p": main["p"], "df": main["df"]})
    return out


def landmark(d: pd.DataFrame, feats: list[str], extra: np.ndarray | None = None):
    """Landmark rows (D-013) of standardised features (+ extra row-level columns) and step
    dummies. Returns X, y, date groups, ticker groups and the row index of each landmark row."""
    x = d[feats].to_numpy(dtype="float64")
    med = np.nanmedian(x, axis=0)
    x = np.where(np.isnan(x), med, x)
    sd = x.std(axis=0)
    x = (x - x.mean(axis=0)) / np.where(sd > 0, sd, 1)
    base = x if extra is None else np.hstack([x, extra])
    dur = np.minimum(d.duration.to_numpy(), FIT_CAP)
    ev = np.where(d.duration.to_numpy() > FIT_CAP, 0, d.event.to_numpy())
    rows, steps, y = expand(dur, ev, MAX_STEP)
    dummies = (steps[:, None] == np.arange(1, MAX_STEP + 1)[None, :]).astype(float)
    X = np.hstack([base[rows], dummies])
    return X, y, d.trade_date.to_numpy()[rows], d.ticker.to_numpy()[rows], rows, x


def fit_clustered(X, y, groups, tickers) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Ridge (C = RIDGE_C) landmark logit; date-clustered and two-way (date x ticker,
    positive semi-definite) sandwich covariances."""
    m = LogisticRegression(C=RIDGE_C, l1_ratio=0.0, fit_intercept=False, max_iter=5000)
    m.fit(X, y)
    b = m.coef_[0]
    p = 1 / (1 + np.exp(-(X @ b)))
    Hi = np.linalg.inv((X * (p * (1 - p))[:, None]).T @ X + np.eye(X.shape[1]) / RIDGE_C)
    r = y - p
    both = pd.factorize(pd.MultiIndex.from_arrays([groups, tickers]))[0]
    Bd = _meat(X, r, groups)
    V2 = _psd(Hi @ (Bd + _meat(X, r, tickers) - _meat(X, r, both)) @ Hi)
    return b, Hi @ Bd @ Hi, V2


def one_sided(b, Vd, V2, j: int, sign: int) -> dict:
    """H0: sign * beta_j <= 0 against sign * beta_j > 0; the larger of the date-clustered and
    two-way p-values decides (D-027 item 5/6)."""
    out = {"coef": float(b[j])}
    for name, V in (("date", Vd), ("two_way", V2)):
        se = float(np.sqrt(max(V[j, j], 0.0)))
        z = sign * b[j] / se if se > 0 else float("nan")
        out[name] = {"se": se, "z": float(z), "p": float(sst.norm.sf(z))}
    out["p"] = max(out["date"]["p"], out["two_way"]["p"])
    out["z"] = min(out["date"]["z"], out["two_way"]["z"])
    return out


def joint_wald(b, Vd, V2, cols) -> dict:
    out = {}
    for name, V in (("date", Vd), ("two_way", V2)):
        bc, Vc = b[cols], _psd(V[np.ix_(cols, cols)])
        stat = float(bc @ np.linalg.pinv(Vc) @ bc)
        out[name] = {"wald": stat, "df": len(cols), "p": float(sst.chi2.sf(stat, len(cols)))}
    out["p"] = max(out["date"]["p"], out["two_way"]["p"])
    return out


D_COLS = [c for c in ABCDx if c.removesuffix("_xdir") in set(BLOCKS["D"])]
PRE_YEARS = 4  # D-027 item 6: matched pre-window
INDEX_PLACEBO_YEARS = range(2016, 2024)


def index_test(ds, sessions, post_date: pd.Timestamp, start: pd.Timestamp,
               end: pd.Timestamp) -> dict:  # fmt: skip
    """D-027 item 6: eta_D = block D's linear index from ABCDx fitted on the sample's
    pre-period; then ABCDx + post + post x eta_D on the sample; H0 lambda <= 0, one-sided."""
    d = censor_at(ds[ds.trade_date >= start], sessions, end)
    X, y, g, t, rows, x = landmark(d, ABCDx)
    pre = (d.trade_date < post_date).to_numpy()[rows]
    m = LogisticRegression(C=RIDGE_C, l1_ratio=0.0, fit_intercept=False, max_iter=5000)
    m.fit(X[pre], y[pre])
    jd = [ABCDx.index(c) for c in D_COLS]
    eta = x[:, jd] @ m.coef_[0][jd]
    eta = (eta - eta.mean()) / (eta.std() or 1.0)
    post = (d.trade_date >= post_date).to_numpy(float)
    X2, y2, g2, t2, _, _ = landmark(d, ABCDx, extra=np.column_stack([post, post * eta]))
    b, Vd, V2 = fit_clustered(X2, y2, g2, t2)
    res = one_sided(b, Vd, V2, len(ABCDx) + 1, +1)
    res.update({"start": str(start.date()), "end": str(end.date()), "rows": int(len(d)),
                "post_rows": int(post.sum())})  # fmt: skip
    return res


def run_index(ds, sessions, announce: pd.Timestamp, study_end: pd.Timestamp,
              placebo_years=None, log=print) -> dict:  # fmt: skip
    """RQ4 primary (D-027 item 6) with matched four-year pre-windows."""
    real = index_test(ds, sessions, announce, announce - pd.DateOffset(years=PRE_YEARS),
                      study_end)  # fmt: skip
    log("index: real computed")
    placebos = {}
    for y in placebo_years if placebo_years is not None else INDEX_PLACEBO_YEARS:
        pd_ = pd.Timestamp(f"{y}-10-07")
        end = min(pd_ + WINDOW, announce - pd.Timedelta(days=1))
        placebos[str(y)] = index_test(ds, sessions, pd_, pd_ - pd.DateOffset(years=PRE_YEARS),
                                      end)  # fmt: skip
        log(f"index: placebo {y} computed")
    beats = all(real["z"] > v["z"] for v in placebos.values())
    return {"real": real, "placebos": placebos, "beats_every_placebo": beats,
            "rank_of_real": 1 + sum(v["z"] >= real["z"] for v in placebos.values()),
            "h4_supported": bool(real["p"] < 0.05 and beats)}  # fmt: skip


def run(ds, sessions, announce: pd.Timestamp, study_end: pd.Timestamp, placebo_years=None,
        log=print) -> dict:  # fmt: skip
    real = wald(*design(censor_at(ds, sessions, study_end), announce))
    log(f"real: computed ({real['clusters_date']} date clusters)")
    placebos = {}
    for y in placebo_years if placebo_years is not None else PLACEBO_YEARS:
        start = pd.Timestamp(f"{y}-10-07")
        end = min(start + WINDOW, announce - pd.Timedelta(days=1))
        placebos[str(y)] = wald(*design(censor_at(ds, sessions, end), start))
        log(f"placebo {y}: computed")
    beats_all = all(real["wald"] > v["wald"] for v in placebos.values())
    rank = 1 + sum(v["wald"] >= real["wald"] for v in placebos.values())
    return {"real": real, "placebos": placebos, "rank_of_real": rank, "beats_every_placebo":
            beats_all, "h4_supported": bool(real["p"] < 0.05 and beats_all)}  # fmt: skip


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - CLI wiring
    from vnbank.research.survival.features.assemble import add_direction_interactions

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--features-run", required=True)
    ap.add_argument(
        "--evaluate-run",
        required=True,
        type=Path,
        help="the passed final.evaluate run of the main cache (protocol section 6)",
    )
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--i-confirm-final-run", action="store_true")
    a = ap.parse_args(argv)
    if not (a.final and a.i_confirm_final_run):
        raise SystemExit("RQ4 uses the test years: it needs --final --i-confirm-final-run")
    commit = code_version()
    fr = Path(a.features_run)
    fcfg = json.loads((fr / "config.json").read_text())
    from vnbank.research.survival.final.evaluate import require_passed_evaluation

    require_passed_evaluation(a.evaluate_run, snapshot=fcfg["snapshot_id"])
    snap = paths.SNAPSHOTS / fcfg["snapshot_id"]
    sessions = np.sort(pd.to_datetime(
        pd.read_parquet(snap / "sessions_hose.parquet").trade_date).to_numpy())  # fmt: skip
    ev = pd.read_csv(paths.SEEDS / "market_classification_events.csv", parse_dates=["event_date"])
    announce = ev.loc[ev.event == CFG["rq4"]["break_event"], "event_date"].iloc[0]
    ds = add_direction_interactions(pd.read_parquet(fr / "dataset.parquet"))
    ds["trade_date"], ds["end_date"] = pd.to_datetime(ds.trade_date), pd.to_datetime(ds.end_date)
    run_dir = paths.runs_dir(1) / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-final-rq4"
    run_dir.mkdir(parents=True)
    end = pd.Timestamp(CFG["study"]["end"])
    res = {"primary_single_index": run_index(ds, sessions, announce, end),  # D-027 item 6
           "secondary_wald_10": run(ds, sessions, announce, end)}  # D-026 5a  # fmt: skip
    (run_dir / "config.json").write_text(json.dumps({
        "git_commit": commit, "features_run": fr.name, "snapshot_id": fcfg["snapshot_id"],
        "announcement": str(announce.date()), "post_terms": POST_TERMS, "ridge_C": RIDGE_C,
        "placebo_years": list(PLACEBO_YEARS), "window": "13 months"}, indent=2))  # fmt: skip
    (run_dir / "metrics.json").write_text(json.dumps(res, indent=1, default=float))
    print(f"done: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
