"""Build the Paper 1 data package for peer review (sent only on request, via the editor).

    uv run python scripts/paper1_review_data.py

Writes data/review/paper1-review-data-<YYYYMMDD>/ (git-ignored) and two zips next to it:

* core: the frozen snapshot 1f0c80b50427479e WITHOUT the separate study's folder (paper2/),
  a manifest restricted to this paper's files, the swing labels and the three feature datasets
  (k = 1.5, 2, 3), a README with terms and reproduction steps, and SHA256SUMS;
* predictions: the saved test-year predictions of the single final run (data/final_cache, main
  design), from which every reported metric can be re-scored without refitting.

Every snapshot file is checked against the hash in the original manifest before it is copied.
No raw provider files, no .env, nothing of the separate study.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

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
EXCLUDED = "paper2/"  # inputs of a separate, unpublished study frozen in the same snapshot
CODE_DOI = "10.5281/zenodo.24589608"

README = """# Data for peer review: "Predictable but Mostly Mechanical: Survival Forecasts of Trend
Reversals in Vietnamese Stocks"

Prepared {date} by the authors for the referees of the Journal of Forecasting.

**For peer review only. Do not redistribute.** The price data are derived from CafeF and Yahoo
Finance, whose terms do not allow redistribution. Please delete the files after the review.

## Contents

- `snapshot/`: the frozen data snapshot `{snap}` behind every reported result: universe, raw
  and adjusted prices, price limits, sessions, VN30 membership, local and global features, bank
  NPL ratios and news counts (Parquet).
- `snapshot/manifest_paper1.json`: the snapshot manifest, restricted to this paper's files (see
  "Verifying" below).
- `labels/`: swing labels and survival rows for k = 1.5, 2 and 3 (run `{labels}`).
- `features/k*/dataset.parquet`: the model datasets for each k (runs in `features/*/config.json`).
- `SHA256SUMS`: hashes of every file in this package.

The test-year predictions of the final run are in a separate archive
(`paper1-review-predictions-{stamp}.zip`, about 400 MB), with one folder per test year.

## Verifying

1. `sha256sum -c SHA256SUMS` checks the package.
2. Each snapshot file's SHA-256 equals the one recorded in the original manifest when the
   snapshot was frozen (copied in `manifest_paper1.json`, `files_sha256`). The snapshot also froze
   the inputs of a separate study; those files are withheld, so the snapshot identifier, a hash
   over all files, cannot be recomputed from this copy, but every file of this paper can be checked.

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

Rebuilt labels and features should match the files in `labels/` and `features/` (compare hashes).
Refitting all models for the ten test years took several hours on a 128-thread machine; the saved
predictions make that unnecessary for checking the reported metrics.
"""


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def zip_dir(src: Path, dest: Path) -> None:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(src.parent))


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    base = REPO / "data" / "review"
    core = base / f"paper1-review-data-{stamp}"
    pred = base / f"paper1-review-predictions-{stamp}"
    for d in (core, pred):
        shutil.rmtree(d, ignore_errors=True)

    # 1. snapshot without the separate study, each file checked against the frozen manifest
    manifest = json.loads((SNAP / "manifest.json").read_text())
    files = {k: v for k, v in manifest["files_sha256"].items() if not k.startswith(EXCLUDED)}
    (core / "snapshot").mkdir(parents=True)
    for name, digest in files.items():
        src = SNAP / name
        if sha256(src) != digest:
            raise SystemExit(f"{name}: hash differs from the frozen manifest")
        shutil.copy2(src, core / "snapshot" / name)
    keep = {
        "snapshot_id": manifest["snapshot_id"],
        "label": manifest["label"],
        "created_at_utc": manifest["created_at_utc"],
        "git_commit": manifest["git_commit"],
        "study_start": manifest["study_start"],
        "study_end": manifest["study_end"],
        "warmup_start": manifest["warmup_start"],
        "files_sha256": files,
        "row_counts": {
            k: v for k, v in manifest["row_counts"].items() if not k.startswith(EXCLUDED[:-1])
        },
        "note": "restricted to the files of this paper; the inputs of a separate study frozen in "
        "the same snapshot are withheld, so snapshot_id cannot be recomputed from this copy",
    }
    (core / "snapshot" / "manifest_paper1.json").write_text(json.dumps(keep, indent=1))

    # 2. labels and features
    (core / "labels").mkdir()
    for p in LABELS.iterdir():
        if p.suffix in (".parquet", ".json"):
            shutil.copy2(p, core / "labels" / p.name)
    for k, run in FEATURES.items():
        (core / "features" / k).mkdir(parents=True)
        for name in ("dataset.parquet", "config.json"):
            shutil.copy2(run / name, core / "features" / k / name)

    # 3. README and hashes
    (core / "README.md").write_text(README.format(
        date=datetime.now(UTC).strftime("%d %B %Y"), snap=SNAP_ID, labels=LABELS.name,
        stamp=stamp, doi=CODE_DOI))  # fmt: skip
    sums = [f"{sha256(p)}  {p.relative_to(core)}" for p in sorted(core.rglob("*")) if p.is_file()]
    (core / "SHA256SUMS").write_text("\n".join(sums) + "\n")

    # 4. predictions of the final run (main design), with their own hashes
    shutil.copytree(CACHE, pred / "main")
    sums = [f"{sha256(p)}  {p.relative_to(pred)}" for p in sorted(pred.rglob("*")) if p.is_file()]
    (pred / "SHA256SUMS").write_text("\n".join(sums) + "\n")

    # 5. nothing of the separate study, then zip
    leaked = [p for d in (core, pred) for p in d.rglob("*") if "paper2" in str(p.relative_to(d))]
    if leaked:
        raise SystemExit(f"separate-study files in the package: {leaked[:3]}")
    for d in (core, pred):
        zip_dir(d, d.with_suffix(".zip"))
        print(f"{d.with_suffix('.zip')}  {d.with_suffix('.zip').stat().st_size / 2**20:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
