"""Specifications of the final run (FINAL_RUN_PROTOCOL.md section 2), built from the development
registries so every feature list is the one pre-registered and used in development.

A spec is (model family, feature list, row set): row set "all" = every survival row, "bank" =
bank rows after block E is added (D-023).
"""

from __future__ import annotations

from vnbank.research.survival.dev_attribution import variants as d018_variants
from vnbank.research.survival.dev_decompose import (
    FEATURES_E,
    SPECS_D016,
    SPECS_D017,
    SPECS_D019,
    SPECS_D020,
    SPECS_D022,
)

ABCDx = SPECS_D017["ABCDx"]
ABCx = SPECS_D017["ABCx"]
ABC, ABCD = SPECS_D016["ABC"], SPECS_D016["ABCD"]
FOREIGN = ["foreign_net_share", "foreign_missing"]  # D-012 robustness: flows + missing indicator

SPECS: dict[str, tuple[str, list[str], str]] = {
    # logistic hazard (landmark, D-013)
    "M": ("logit", SPECS_D016["M"], "all"),
    "DIST": ("logit", SPECS_D019["DIST"], "all"),
    "AGE": ("logit", SPECS_D019["AGE"], "all"),
    "ABC": ("logit", ABC, "all"),
    "ABCD": ("logit", ABCD, "all"),
    "ABCx": ("logit", ABCx, "all"),
    "ABCDx": ("logit", ABCDx, "all"),  # main specification (D-017)
    "MBCx": ("logit", SPECS_D017["MBCx"], "all"),
    "MBCDx": ("logit", SPECS_D017["MBCDx"], "all"),
    "ABCDx_bank": ("logit", SPECS_D020["ABCDx_bank"], "all"),
    "ABCDx_ff": ("logit", [*ABCDx, *FOREIGN], "all"),
    # other families
    "cox_ABCx": ("cox", ABCx, "all"),
    "cox_ABCDx": ("cox", ABCDx, "all"),
    "gbm_ABC": ("gbm", ABC, "all"),
    "gbm_ABCD": ("gbm", ABCD, "all"),
    "rsf_ABC": ("rsf", ABC, "all"),
    "rsf_ABCD": ("rsf", ABCD, "all"),
    "nn_seq_ABCD": (*SPECS_D022["nn_seq_ABCD"], "all"),
    "nn_seq_ABC": (*SPECS_D022["nn_seq_ABC"], "all"),
    "nn_static_ABCD": (*SPECS_D022["nn_static_ABCD"], "all"),
    # block E, bank rows (D-023)
    "bank_M": ("logit", SPECS_D016["M"], "bank"),
    "bank_M_E": ("logit", [*SPECS_D016["M"], *FEATURES_E], "bank"),
    "bank_ABCDx": ("logit", ABCDx, "bank"),
    "bank_ABCDx_E": ("logit", [*ABCDx, *FEATURES_E], "bank"),
}

# D-023 robustness: block E built differently; each re-tunes M_E and ABCDx_E on bank rows
E_VARIANTS = ("ocr_only", "margin0", "margin20", "all_aliases")
E_VARIANT_SPECS = ("bank_M_E", "bank_ABCDx_E")

# D-018: leave-one-out and gold/GPR variants of ABCDx, refitted with ABCDx's parameters
LOO = {k: v for k, v in d018_variants().items() if k != "ABCDx"}

# D-013 / D-022 / D-025 shuffled-label controls: spec -> number of permutations
SHUFFLED = {"ABCD": 10, "ABCDx": 10, "M": 10, "nn_seq_ABCD": 3}

# D-025 sensitivity: censor at the fold boundary instead of purging
BOUNDARY = ("M", "ABCx", "ABCDx")

# D-021 trading test: inner-year predictions for tau
BACKTEST = ("ABCDx", "M")

# Pairs compared in the pooled evaluation (hi, lo), FINAL_RUN_PROTOCOL.md section 4
DIFFS = [
    ("ABCDx", "km"), ("ABCx", "M"), ("ABCDx", "M"), ("nn_seq_ABCD", "M"),  # RQ1, D-016
    ("ABCDx", "ABCx"), ("MBCDx", "MBCx"), ("ABCD", "ABC"), ("cox_ABCDx", "cox_ABCx"),
    ("gbm_ABCD", "gbm_ABC"), ("rsf_ABCD", "rsf_ABC"), ("nn_seq_ABCD", "nn_seq_ABC"),  # RQ2
    ("ABCDx_bank", "ABCDx"),  # RQ2 banks, D-020
    ("M", "DIST"), ("AGE", "km"), ("DIST", "km"),  # RQ3, D-019
    ("nn_seq_ABCD", "nn_static_ABCD"), ("nn_seq_ABCD", "ABCDx"),  # D-022
    ("ABCDx_ff", "ABCDx"), ("ABCDx_ff", "M"),  # D-012 robustness
]  # fmt: skip
# RQ1 / H1: every model against Kaplan-Meier (protocol section 4)
DIFFS += [(n, "km") for n, (_, _, rows) in SPECS.items()
          if rows == "all" and (n, "km") not in DIFFS]  # fmt: skip
BANK_DIFFS = [
    ("bank_ABCDx_E", "bank_ABCDx"),
    ("bank_M_E", "bank_M"),
    ("bank_ABCDx", "bank_km"),
    ("bank_M", "bank_km"),
]  # D-023; RQ1 on bank rows


def all_features() -> set[str]:
    out = set()
    for _, feats, _ in SPECS.values():
        out.update(feats)
    for feats in LOO.values():
        out.update(feats)
    return out
