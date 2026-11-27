"""Post-hoc comparisons on the cached final-run predictions (D-031; added after the referee-style
review of 2026-11-27, so every result here is labelled post hoc and none changes a pre-registered
decision).

    uv run python -m vnbank.research.survival.final.posthoc

No model is refitted and no test-year prediction is recomputed: the per-year caches of the
single final run (data/final_cache/vnbank/cache/main) are re-scored with the evaluation code of
the final run (``final.evaluate``), the same year-stratified metrics, the same moving-block
bootstrap (blocks of 20 sessions, 1,000 resamples) and the same decision rule.

Comparisons:
* like for like against the boosted mechanical baseline M_flex: every non-linear model of the
  same feature blocks (gbm, rsf, neural) minus M_flex (the pre-registered H1-mech pair was the
  linear ABCx against the boosted M_flex);
* the stepwise decomposition KM -> RW -> M_flex -> ABCx and -> nn_seq_ABC, on both metrics.

Writes research/paper1/runs/<UTC timestamp>-final-posthoc/{config.json, metrics.json}.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from vnbank.common import paths
from vnbank.research.shared.run_meta import code_version
from vnbank.research.survival.final import evaluate as E
from vnbank.research.survival.final import specs as S

CACHE = paths.REPO / "data" / "final_cache" / "vnbank" / "cache" / "main"
YEARS = list(range(2017, 2027))
LIKE_FOR_LIKE = [("gbm_ABC", "M_flex"), ("rsf_ABC", "M_flex"), ("nn_static_ABCD", "M_flex"),
                 ("nn_seq_ABC", "M_flex"), ("nn_seq_ABCD", "M_flex"), ("gbm_ABCD", "M_flex"),
                 ("rsf_ABCD", "M_flex")]  # fmt: skip
DECOMPOSITION = [("RW", "km"), ("M_flex", "RW"), ("ABCx", "M_flex"), ("nn_seq_ABC", "M_flex")]


def main(argv: list[str] | None = None) -> int:
    commit = code_version()
    if commit.endswith("+dirty"):
        raise SystemExit("working tree is dirty: reported results come from committed code")
    c = E.load_caches(CACHE, YEARS)
    keys, preds = c["keys"], c["preds"]
    ctx = E.context(c, YEARS)
    tests = {f"{a}-{b}": [(a, b)] for a, b in LIKE_FOR_LIKE + DECOMPOSITION}
    res = E.primaries(ctx, keys, preds, tests, n=S.PRIMARY_RESAMPLES)
    out = paths.runs_dir(1) / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-final-posthoc"
    out.mkdir(parents=True)
    (out / "config.json").write_text(json.dumps(
        {"git_commit": commit, "created_at_utc": datetime.now(UTC).isoformat(),
         "decision": "D-031 (post hoc)", "cache": str(CACHE.relative_to(paths.REPO)),
         "years": YEARS, "resamples": S.PRIMARY_RESAMPLES,
         "like_for_like": LIKE_FOR_LIKE, "decomposition": DECOMPOSITION}, indent=1))  # fmt: skip
    (out / "metrics.json").write_text(json.dumps(res, indent=1))
    for k, v in res.items():
        d = v["pairs"][k]
        print(
            f"{k:28s} improves={d['improves']!s:5s} dC [{d['c']['lo']:+.4f}, {d['c']['hi']:+.4f}]"
            f" dIBS [{d['ibs']['lo']:+.4f}, {d['ibs']['hi']:+.4f}]"
        )
    print(out.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
