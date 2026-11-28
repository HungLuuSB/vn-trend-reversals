"""Build the Paper 1 data packages: one for peer review, one for approved requests.

    uv run python scripts/paper1_review_data.py

Writes, under the git-ignored data/release/:

* paper1-data-review-<YYYYMMDD>.zip and paper1-predictions-review-<YYYYMMDD>.zip, for the editor
  and referees (sent only on request, via the editor; to be deleted after the review);
* paper1-data-research-<YYYYMMDD>.zip and paper1-predictions-research-<YYYYMMDD>.zip, for people
  whose access request is approved (the restricted Zenodo record).

Both versions hold the same files and differ only in their README (audience and terms of use):

* data: the frozen snapshot 1f0c80b50427479e WITHOUT the separate study's folder (paper2/), a
  manifest restricted to this paper's files, the swing labels and the three feature datasets
  (k = 1.5, 2, 3), a README with a data dictionary, terms and reproduction steps, and SHA256SUMS;
* predictions: the saved test-year predictions of the single final run (main design), from which
  every reported metric can be re-scored without refitting, with a README and SHA256SUMS.

Every snapshot file is checked against the hash in the original manifest before it is copied.
No raw provider files, no .env, nothing of the separate study.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.parquet as pq

REPO = Path(__file__).resolve().parents[1]
SNAP_ID = "1f0c80b50427479e"
SNAP = REPO / "data" / "snapshots" / SNAP_ID
RUNS = REPO / "research" / "paper1" / "runs"
LABELS = RUNS / f"20261126T052329Z-labels-{SNAP_ID}"
FEATURES = {
    "k2": RUNS / f"20261126T052338Z-features-{SNAP_ID}-k2",
    "k1_5": RUNS / f"20261126T052339Z-features-{SNAP_ID}-k1_5",
    "k3": RUNS / f"20261126T052341Z-features-{SNAP_ID}-k3",
}
CACHE = REPO / "data" / "final_cache" / "vnbank" / "cache" / "main"
OUT = REPO / "data" / "release"
EXCLUDED = "paper2/"  # inputs of a separate, unpublished study frozen in the same snapshot
CODE_DOI = "10.5281/zenodo.24589608"
TITLE = (
    "Predictable but Mostly Mechanical: Survival Forecasts of Trend Reversals in Vietnamese Stocks"
)
CONTACT = "Thai Hung Luu, hung.luu.research@gmail.com"

AUDIENCE = {
    "review": {
        "who": "Prepared by the authors for the editor and referees of the Journal of Forecasting.",
        "terms": [
            "**For peer review only.** Use the files only to assess the manuscript.",
            "Do not redistribute the files or any part of them.",
            "Please delete the files when the review is complete.",
        ],
    },
    "research": {
        "who": "Provided by the authors to researchers whose access request was approved.",
        "terms": [
            "**For verification and non-commercial research only.**",
            "Do not redistribute the files or any part of the price data; results derived from "
            "them may be published.",
            "Cite the paper and this data record when you use them.",
        ],
    },
}
WHY_RESTRICTED = (
    "The price data are derived from CafeF and Yahoo Finance, whose terms do not allow "
    "redistribution; this is why access is restricted."
)

# what each file holds and where it comes from (the data dictionary in the README)
DESCRIBE = {
    "universe_daily.parquet": (
        "The research universe per HOSE session: VN30 members as of each date and every listed "
        "bank, with flags for VN30, bank, UPCoM and whether a price exists. Source: VN30 baskets "
        "and changes, bank listings (sourced seeds in the code repository)."
    ),
    "vn30_membership.parquet": (
        "Point-in-time VN30 membership spells with announcement dates and a source URL per entry. "
        "Source: HOSE and press announcements."
    ),
    "bank_spells.parquet": (
        "Listing spells of every Vietnamese bank: exchange, first and last trade date, why the "
        "spell ended, source URL."
    ),
    "sessions_hose.parquet": "The HOSE trading calendar with a session counter.",
    "prices_raw.parquet": (
        "Daily raw (unadjusted) open, high, low and close in VND and volume per stock, with "
        "available_at_utc (the 15:00 Vietnam time close) and the raw-archive key. "
        "Source: CafeF end-of-day archives."
    ),
    "prices_adjusted.parquet": (
        "Prices back-adjusted for dividends, splits and rights issues by the authors' own "
        "corporate-action factors; for returns and ratios only, never for price levels."
    ),
    "corporate_actions.parquet": (
        "Adjustment ratio per ex-date, its verification status and source URLs (exchange, "
        "depository or company notices)."
    ),
    "price_limits.parquet": (
        "Exchange reference price, daily ceiling and floor and limit hits per stock-day, using "
        "the rules in force on each date; limit_status marks days whose limit cannot be computed "
        "(never guessed)."
    ),
    "local_market.parquet": (
        "VN-Index and VN30 closes and returns, advancing and declining counts, HOSE matched value "
        "and foreign net flows per session, with available_at_utc."
    ),
    "global_features.parquet": (
        "Overnight global series per Vietnamese session (S&P 500, Nasdaq, dollar index, gold, "
        "Brent, Hang Seng, Shanghai Composite, USD/VND, USD/CNY, VIX, US 10-year yield, "
        "geopolitical risk), each the last value public before 09:00 Vietnam time "
        "(decision_time_utc). Sources: Yahoo Finance, FRED, Caldara and Iacoviello (2022)."
    ),
    "block_e_npl.parquet": (
        "First-released quarterly non-performing-loan ratio per bank (groups 3-5 over all loans), "
        "with the file's creation time, when it becomes usable (available_at), and whether it was "
        "read by OCR or transcribed from the page image. Source: CafeF filing archive."
    ),
    "news_counts.parquet": (
        "Daily count of CafeF news articles mentioning each bank (09:00 to 09:00) and the count "
        "relative to its 20-session mean, with unambiguous names and with all aliases."
    ),
    "survival_k*.parquet": (
        "Survival rows (one per stock-session inside an open swing) for threshold multiple k: "
        "direction, age, threshold, running extreme, duration to confirmation, event indicator "
        "and censoring reason."
    ),
    "reversals_k*.parquet": (
        "Every confirmed directional-change reversal for k: extreme and confirmation dates and "
        "prices."
    ),
    "dataset.parquet": (
        "The model dataset for k: the survival rows joined with all features of blocks A-E as "
        "used at 09:00 on the next session (definitions in Appendix S1, Table S3, of the paper)."
    ),
}

DATA_README = """# Data for: "{title}"

{who} Version of {date}.

## Terms of use

{terms}
- {why}
- Contact: {contact}.

## Contents

- `snapshot/`: the frozen data snapshot `{snap}` behind every reported result (Parquet).
- `snapshot/manifest_paper1.json`: the snapshot manifest, restricted to this paper's files.
- `labels/`: swing labels and survival rows for k = 1.5, 2 and 3 (run `{labels}`), with a
  summary of the label build (`summary.json`).
- `features/k*/dataset.parquet`: the model datasets for each k (runs in `features/*/config.json`).
- `SHA256SUMS`: hashes of every file in this package.

The test-year predictions of the final run are in a companion archive, with its own README.

## Data dictionary

All times are UTC unless stated; Vietnam is UTC+7. A value may enter a feature only if it was
public before 09:00 Vietnam time on the next session (`available_at_utc`, `decision_time_utc`).

{dictionary}
## Verifying

1. `sha256sum -c SHA256SUMS` checks the package.
2. Each snapshot file's SHA-256 equals the one recorded in the original manifest when the snapshot
   was frozen (`manifest_paper1.json`, `files_sha256`). The snapshot also froze the inputs of a
   separate study; those files are withheld, so the snapshot identifier, a hash over all files,
   cannot be recomputed from this copy, but every file of this paper can be checked.

## Reproducing

The code, decision log and run records are at https://doi.org/{doi}; commit ids recorded in run
folders map to the public repository through `research/paper1/COMMIT_MAP.md`.

```bash
# in a checkout of the code (Python 3.12 with uv)
uv sync
mkdir -p data/snapshots && cp -r <package>/snapshot data/snapshots/{snap}
uv run python -m vnbank.research.swings.build --snapshot {snap} --k 2 --k 1.5 --k 3
uv run python -m vnbank.research.survival.features.assemble --snapshot {snap} \\
    --labels-run research/paper1/runs/<the labels run just written> --k 2
# re-score every reported metric from the saved predictions (no refitting):
uv run python -m vnbank.research.survival.final.evaluate --cache <predictions>/main \\
    --final --i-confirm-final-run
# the paper's numbers from the logged runs:
uv run python -m vnbank.research.survival.report
```

Rebuilt labels and features should match the files in `labels/` and `features/` (compare
hashes). Refitting all models for the ten test years took several hours on a 64-core machine;
the saved predictions make that unnecessary for checking the reported metrics.
"""

PRED_README = """# Test-year predictions of the final run: "{title}"

{who} Version of {date}. Companion to the data package of the same version.

## Terms of use

{terms}
- Contact: {contact}.

## What this is

The saved outputs of the single final walk-forward run (main design, k = 2) on the test years
2017-2026. Every metric reported in the paper can be recomputed from them without refitting.

## Layout

`main/<year>/`, one folder per test year:

- `keys.parquet`: one row per test survival row, in the order of the predictions: ticker,
  trade_date, outcome (`duration`, `event`) and the subgroup flags used in the paper.
- `preds/<model>.npy`: float32 array of shape (rows, 20), the predicted probability that the
  swing has not yet reversed after 1..20 sessions, S(h | x), per model specification (`ABCDx` is
  the main model, `km` Kaplan-Meier, `RW` the random-walk null, `M` and `M_flex` the mechanical
  baselines; names starting with `shuffled` are the shuffled-outcome controls).
- `train_y.npz`: durations and events of that year's training window (for the censoring weights
  of the C-index and the Brier score).
- `bank_keys.parquet`, `bank_preds/`, `bank_train_y.npz`: the same for the bank-row block E
  comparisons.
- `inner_p5.parquet`: inner-validation five-session reversal probabilities used to choose the
  trading threshold.
- `meta.json`: chosen hyperparameters, code commit, snapshot id, feature run, software versions
  and run time.
- `log_<year>.txt`: run logs.

In Python: `numpy.load("main/2017/preds/ABCDx.npy")` and
`pandas.read_parquet("main/2017/keys.parquet")`.

## Re-scoring

With the code at https://doi.org/{doi}:

```bash
uv run python -m vnbank.research.survival.final.evaluate --cache <this folder>/main \\
    --final --i-confirm-final-run
```

`SHA256SUMS` lists the hash of every file (`sha256sum -c SHA256SUMS`).
"""


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_sums(root: Path) -> None:
    lines = [f"{sha256(p)}  {p.relative_to(root)}" for p in sorted(root.rglob("*")) if p.is_file()]
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n")


def zip_dir(src: Path) -> Path:
    dest = src.with_suffix(".zip")
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(src.parent))
    return dest


def dictionary(root: Path) -> str:
    """Markdown data dictionary: what, rows, date range and columns of every Parquet file."""
    out = []
    order = {"snapshot": 0, "labels": 1, "features": 2}  # reading order: data, labels, features
    for p in sorted(root.rglob("*.parquet"), key=lambda p: (order[p.parts[len(root.parts)]], p)):
        t = pq.read_table(p)
        key = p.name if p.name in DESCRIBE else re.sub(r"_k[0-9_]+\.", "_k*.", p.name)
        span = ""
        for col in ("trade_date", "valid_from", "first_trade_date", "ex_date", "confirm_date"):
            if col in t.column_names:
                lo, hi = (str(f(t[col]).as_py()).removesuffix(" 00:00:00")
                          for f in (pc.min, pc.max))  # fmt: skip
                span = f"; `{col}` from {lo} to {hi}"
                break
        cols = ", ".join(f"`{c}`" for c in t.column_names)
        out.append(
            f"### `{p.relative_to(root)}`\n\n{DESCRIBE.get(key, '')}\n\n"
            f"{t.num_rows:,} rows, {t.num_columns} columns{span}.\n\nColumns: {cols}\n"
        )
    return "\n".join(out)


def build_data(dest: Path) -> None:
    """Snapshot (checked against the frozen manifest, separate study removed), labels, features."""
    manifest = json.loads((SNAP / "manifest.json").read_text())
    files = {k: v for k, v in manifest["files_sha256"].items() if not k.startswith(EXCLUDED)}
    (dest / "snapshot").mkdir(parents=True)
    for name, digest in files.items():
        if sha256(SNAP / name) != digest:
            raise SystemExit(f"{name}: hash differs from the frozen manifest")
        shutil.copy2(SNAP / name, dest / "snapshot" / name)
    keep = {k: manifest[k] for k in ("snapshot_id", "label", "created_at_utc", "git_commit",
                                     "study_start", "study_end", "warmup_start")}  # fmt: skip
    keep["files_sha256"] = files
    keep["row_counts"] = {
        k: v for k, v in manifest["row_counts"].items() if not k.startswith(EXCLUDED[:-1])
    }
    keep["note"] = (
        "restricted to the files of this paper; the inputs of a separate study frozen in the "
        "same snapshot are withheld, so snapshot_id cannot be recomputed from this copy"
    )
    (dest / "snapshot" / "manifest_paper1.json").write_text(json.dumps(keep, indent=1))
    (dest / "labels").mkdir()
    for p in LABELS.iterdir():
        if p.suffix in (".parquet", ".json"):
            shutil.copy2(p, dest / "labels" / p.name)
    for k, run in FEATURES.items():
        (dest / "features" / k).mkdir(parents=True)
        for name in ("dataset.parquet", "config.json"):
            shutil.copy2(run / name, dest / "features" / k / name)


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    date = datetime.now(UTC).strftime("%d %B %Y")
    built = []
    for audience, a in AUDIENCE.items():
        terms = "\n".join(f"- {t}" for t in a["terms"])
        data = OUT / f"paper1-data-{audience}-{stamp}"
        pred = OUT / f"paper1-predictions-{audience}-{stamp}"
        for d in (data, pred):
            shutil.rmtree(d, ignore_errors=True)
            d.with_suffix(".zip").unlink(missing_ok=True)

        build_data(data)
        (data / "README.md").write_text(DATA_README.format(
            title=TITLE, who=a["who"], date=date, terms=terms, why=WHY_RESTRICTED,
            contact=CONTACT, snap=SNAP_ID, labels=LABELS.name, doi=CODE_DOI,
            dictionary=dictionary(data)))  # fmt: skip
        write_sums(data)

        shutil.copytree(CACHE, pred / "main")
        (pred / "README.md").write_text(PRED_README.format(
            title=TITLE, who=a["who"], date=date, terms=terms, contact=CONTACT,
            doi=CODE_DOI))  # fmt: skip
        write_sums(pred)

        for d in (data, pred):
            if any("paper2" in str(p.relative_to(d)) for p in d.rglob("*")):
                raise SystemExit(f"separate-study files in {d.name}")
            built.append(zip_dir(d))
    for z in built:
        print(f"{z}  {z.stat().st_size / 2**20:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
