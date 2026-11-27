"""Paper 1 numbers, tables and figures from the final runs (research/paper1/configs/report.yaml).

    uv run python -m vnbank.research.survival.report

Writes papers/paper1/generated/: numbers.tex (one macro per reported number, with its source),
tab_*.tex (booktabs tabular bodies) and fig_*.tex (pgfplots bodies, so no plotting dependency is
needed). Every number in the paper comes from here (CLAUDE.md); nothing is typed by hand.

Sources: the single final walk-forward run (D-024, D-026, D-027) and the frozen snapshot it used.
Conventions: C-indices with 3 decimals, integrated Brier scores (IBS) with 4; differences are
"model A minus model B", so a better A has dC > 0 and dIBS < 0.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import yaml

from vnbank.common import paths
from vnbank.research.shared import report as R
from vnbank.research.shared.run_meta import code_version

PAPER = 1
REGISTRY = paths.paper_dir(PAPER) / "configs" / "report.yaml"
OUT = paths.REPO / "papers" / "paper1" / "generated"
STUDY_START, STUDY_END, TEST_START = "2012-01-03", "2026-11-20", "2017-01-01"

# display names; the order is the order of the model table
MODELS: list[tuple[str, str, str]] = [  # (id, group, label)
    ("km", "Benchmarks", "Kaplan--Meier"),
    ("RW", "Benchmarks", "Random-walk null (\\texttt{RW})"),
    ("AGE", "Mechanical", "Age only (\\texttt{AGE})"),
    ("DIST", "Mechanical", "Distance only (\\texttt{DIST})"),
    ("M", "Mechanical", r"Age and distance (\texttt{M})"),
    ("M_flex", "Mechanical", "Boosted age and distance (\\texttt{M\\_flex})"),
    ("DIST_s", "Mechanical", "Spline distance (\\texttt{DIST\\_s})"),
    ("M_s", "Mechanical", "Spline distance and age (\\texttt{M\\_s})"),
    ("ABC", "Logistic hazard", "\\texttt{ABC}"),
    ("ABCD", "Logistic hazard", "\\texttt{ABCD}"),
    ("ABCx", "Logistic hazard", "\\texttt{ABCx}"),
    ("ABCDx", "Logistic hazard", "\\texttt{ABCDx} (main)"),
    ("MBCx", "Logistic hazard", "\\texttt{MBCx}"),
    ("MBCDx", "Logistic hazard", "\\texttt{MBCDx}"),
    ("ABCDx_bank", "Logistic hazard", "\\texttt{ABCDx\\_bank}"),
    ("ABCDx_ff", "Logistic hazard", "\\texttt{ABCDx} + foreign flows"),
    ("cox_ABCx", "Other families", "Cox, \\texttt{ABCx}"),
    ("cox_ABCDx", "Other families", "Cox, \\texttt{ABCDx}"),
    ("gbm_ABC", "Other families", "Boosted hazard, \\texttt{ABC}"),
    ("gbm_ABCD", "Other families", "Boosted hazard, \\texttt{ABCD}"),
    ("rsf_ABC", "Other families", "Random survival forest, \\texttt{ABC}"),
    ("rsf_ABCD", "Other families", "Random survival forest, \\texttt{ABCD}"),
    ("nn_static_ABCD", "Other families", "Neural, static, \\texttt{ABCD}"),
    ("nn_seq_ABC", "Other families", "Neural, sequence, \\texttt{ABC}"),
    ("nn_seq_ABCD", "Other families", "Neural, sequence, \\texttt{ABCD}"),
]
LABEL = {m: lab for m, _, lab in MODELS}
PRIMARY = [  # (key in metrics.json, hypothesis label)
    ("H1", "H1: predictable"),
    ("H1_mech", "H1-mech: beyond the mechanics"),
    ("H2", "H2: global information"),
    ("H3", "H3: trends age"),
    ("E", "Block E: bank fundamentals and news"),
]
SECONDARY = [  # paired comparisons shown in the secondary table, in this order
    ("ABCx-M", "Local features vs mechanical"),
    ("ABCDx-M", "Main model vs mechanical"),
    ("nn_seq_ABCD-M", "Neural vs mechanical"),
    ("ABCDx-M_flex", "Main model vs boosted mechanical"),
    ("ABCDx-RW", "Main model vs random walk"),
    ("M_flex-RW", "Boosted mechanical vs random walk"),
    ("M-M_flex", "Linear vs boosted mechanical"),
    ("DIST-km", "Distance only vs Kaplan--Meier"),
    ("AGE-km", "Age only vs Kaplan--Meier"),
    ("M-DIST", "Age added to distance (linear)"),
    ("MBCDx-MBCx", "Global block, mechanical base"),
    ("ABCD-ABC", "Global block, no direction terms"),
    ("cox_ABCDx-cox_ABCx", "Global block, Cox"),
    ("gbm_ABCD-gbm_ABC", "Global block, boosted hazard"),
    ("rsf_ABCD-rsf_ABC", "Global block, random survival forest"),
    ("nn_seq_ABCD-nn_seq_ABC", "Global block, neural"),
    ("ABCDx_bank-ABCDx", "Bank interactions"),
    ("nn_seq_ABCD-nn_static_ABCD", "Price sequence in the neural model"),
    ("nn_seq_ABCD-ABCDx", "Neural vs main model"),
    ("ABCDx_ff-ABCDx", "Foreign flows added"),
]
YEARS = list(range(2017, 2027))
STRATEGIES = [
    ("model", r"\relax Model exit (\texttt{ABCDx})"),
    ("mech", r"\relax Mechanical exit (\texttt{M})"),
    ("dc", "Directional-change exit"),
    ("bh", "Buy-and-hold"),
]
SLICE_LABEL = {
    "2017-2019": "2017–2019",
    "2020-2021": "2020–2021",
    "2023-2026": "2023–2026",
    "banks": "Banks",
    "vn30_non_banks": "VN30, non-banks",
    "no_upcom_banks": "Without UPCoM-only banks",
    "no_limit_close": "Known limits, no close at the limit",
}
K_LABEL = {"k1_5": "1.5", "k2": "2", "k3": "3"}


def registry() -> dict:
    return yaml.safe_load(REGISTRY.read_text())


def tok(model: str) -> str:
    """Macro-safe token for a model or pair id ("nn_seq_ABCD-M" -> "NnSeqABCDM")."""
    return R.macro(*[p for p in model.replace("-", "_").split("_") if p])


def model_label(m: str) -> str:
    """Kaplan-Meier prints as KM, every other specification in typewriter type."""
    return "KM" if m in ("km", "bank_km") else rf"\texttt{{{R.escape(m)}}}"


def pair_label(a: str, b: str) -> str:
    return r"\relax " + model_label(a) + " $-$ " + model_label(b)


def pval(p: float) -> str:
    return r"\ensuremath{<0.001}" if p < 0.0005 else R.num(p, 3)


def ci_c(d: dict) -> str:
    return R.interval(d["lo"], d["hi"], 3)


def ci_ibs(d: dict) -> str:
    return R.interval(d["lo"], d["hi"], 4)


def yes(b: bool) -> str:
    return "Yes" if b else "No"


# ------------------------------------------------------------------ evaluation (main, k = 2)


def evaluation(n: R.Numbers, t: dict[str, str], run: R.Run) -> dict:
    r = run.json("metrics.json")
    pm, paired = r["pooled"]["metrics"], r["pooled"]["paired"]
    if r["stop_checks"]["stop"]:
        raise R.ReportError("the evaluation hit a stop rule; nothing may be reported")

    # stop checks and shuffled controls
    sh = r["stop_checks"]["shuffled"]
    for k, v in sh.items():
        n.add(
            R.macro("Shuffled", tok(k.split(":", 1)[1])),
            R.num(v["mean"], 3),
            run,
            f"stop_checks.shuffled.{k}.mean",
        )
    n.add("ShuffledMax", R.num(max(v["mean"] for v in sh.values()), 3), run, "max shuffled mean")
    n.add("ShuffledMin", R.num(min(v["mean"] for v in sh.values()), 3), run, "min shuffled mean")
    n.add(
        "MaxModelC",
        R.num(max(m["uno_c_strat"] for m in pm.values()), 3),
        run,
        "max pooled uno_c_strat over models",
    )

    # every model's pooled metrics
    for m, v in pm.items():
        if m.startswith("boundary:"):
            continue
        tk = tok(m)
        n.add(R.macro("C", tk), R.num(v["uno_c_strat"], 3), run, f"pooled.metrics.{m}.uno_c_strat")
        n.add(R.macro("IBS", tk), R.num(v["ibs_strat"], 4), run, f"pooled.metrics.{m}.ibs_strat")
        n.add(
            R.macro("CDate", tk),
            R.num(v["uno_c_date_strat"], 3),
            run,
            f"pooled.metrics.{m}.uno_c_date_strat",
        )
        for h, w in (("5", "Five"), ("10", "Ten"), ("20", "Twenty")):
            n.add(
                R.macro("AUC", w, tk),
                R.num(v["td_auc"][h], 3),
                run,
                f"pooled.metrics.{m}.td_auc.{h}",
            )

    # every paired difference (200 resamples) as intervals
    for pair, ok in paired["improves"].items():
        tk = tok(pair)
        n.add(
            R.macro("DC", tk), ci_c(paired["ci"][f"{pair}:uno_c"]), run, f"paired.ci.{pair}:uno_c"
        )
        n.add(
            R.macro("DIBS", tk), ci_ibs(paired["ci"][f"{pair}:ibs"]), run, f"paired.ci.{pair}:ibs"
        )
        n.add(R.macro("Improves", tk), yes(ok), run, f"paired.improves.{pair}")
    n.add("PairedResamples", R.integer(paired["resamples"]), run, "paired.resamples")
    n.add("PairedBlock", R.integer(paired["block"]), run, "paired.block")

    # pre-registered primaries (1,000 resamples)
    rows, holm = [], r["primary_holm"]
    mc = 0.0
    for key, lab in PRIMARY:
        v = r["primary"][key]
        n.add(
            R.macro("Prim", key, "Supported"), yes(v["supported"]), run, f"primary.{key}.supported"
        )
        n.add(R.macro("Prim", key, "P"), pval(v["p"]), run, f"primary.{key}.p")
        n.add(R.macro("Prim", key, "Holm"), pval(holm[key]), run, f"primary_holm.{key}")
        for i, (pair, d) in enumerate(v["pairs"].items()):
            tk = tok(pair)
            n.add(R.macro("PrimDC", tk), ci_c(d["c"]), run, f"primary.{key}.pairs.{pair}.c")
            n.add(R.macro("PrimDIBS", tk), ci_ibs(d["ibs"]), run, f"primary.{key}.pairs.{pair}.ibs")
            n.add(R.macro("PrimP", tk), pval(d["p"]), run, f"primary.{key}.pairs.{pair}.p")
            mc = max(mc, *d["mc_error"].values())
            a, b = pair.split("-")
            rows.append(
                {
                    "Hypothesis": lab if i == 0 else "",
                    "Comparison": pair_label(a, b),
                    "dC": ci_c(d["c"]),
                    "dIBS": ci_ibs(d["ibs"]),
                    "p": pval(d["p"]),
                    "Holm": pval(holm[key]) if i == 0 else "",
                    "Supported": yes(v["supported"]) if i == 0 else "",
                }
            )
    n.add(
        "PrimResamples",
        R.integer(next(iter(r["primary"]["H1"]["pairs"].values()))["c"]["n"]),
        run,
        "primary.H1.pairs.*.c.n",
    )
    n.add("PrimMCError", R.num(mc, 4), run, "max primary mc_error")
    n.add("PrimCount", R.integer(len(PRIMARY)), run, "number of primary tests")
    n.add(
        "PrimSupportedCount",
        R.integer(sum(r["primary"][k]["supported"] for k, _ in PRIMARY)),
        run,
        "primaries supported",
    )
    t["tab_primary"] = R.tabular(
        pd.DataFrame(rows),
        align="llccccc",
        header=[
            "Hypothesis",
            "Comparison",
            r"$\Delta C$ (95\% CI)",
            r"$\Delta$IBS (95\% CI)",
            "$p$",
            "Holm $p$",
            "Supported",
        ],
    )

    # model table
    rows, last = [], None
    for m, g, lab in MODELS:
        v = pm[m]
        if g != last:
            rows.append({"Model": rf"\multicolumn{{7}}{{l}}{{\textit{{{g}}}}}"})
            last = g
        rows.append(
            {
                "Model": r"\quad " + lab,
                "C": R.num(v["uno_c_strat"], 3),
                "IBS": R.num(v["ibs_strat"], 4),
                "Cd": R.num(v["uno_c_date_strat"], 3),
                "A5": R.num(v["td_auc"]["5"], 3),
                "A10": R.num(v["td_auc"]["10"], 3),
                "A20": R.num(v["td_auc"]["20"], 3),
            }
        )
    df = pd.DataFrame(rows).fillna("")
    body = R.tabular(
        df,
        align="lcccccc",
        header=["Model", "C", "IBS", "C within dates", "AUC(5)", "AUC(10)", "AUC(20)"],
    )
    # a group row is one multicolumn cell: drop the empty cells tabular() appended to it
    t["tab_models"] = (
        "\n".join(
            ln.split(" & ")[0] + r" \\" if ln.startswith(r"\multicolumn") else ln
            for ln in body.splitlines()
        )
        + "\n"
    )

    # secondary comparisons
    cw, dm, rows = r["pooled"]["clark_west"], r["pooled"]["diebold_mariano"], []
    for pair, lab in SECONDARY:
        a, b = pair.split("-")
        rows.append(
            {
                "Comparison": lab,
                "Models": pair_label(a, b),
                "dC": ci_c(paired["ci"][f"{pair}:uno_c"]),
                "dIBS": ci_ibs(paired["ci"][f"{pair}:ibs"]),
                "Imp": yes(paired["improves"][pair]),
                "CW": pval(cw[pair]["p_one_sided"]) if pair in cw else r"\textemdash{}",
                "DM": pval(dm[pair]["p"]) if pair in dm else r"\textemdash{}",
            }
        )
    t["tab_secondary"] = R.tabular(
        pd.DataFrame(rows),
        align="llccccc",
        header=[
            "Comparison",
            "Models",
            r"$\Delta C$ (95\% CI)",
            r"$\Delta$IBS (95\% CI)",
            "Improves",
            "Clark--West $p$",
            "Diebold--Mariano $p$",
        ],
    )
    for pair, v in cw.items():
        n.add(R.macro("CW", tok(pair)), R.num(v["cw"], 2), run, f"clark_west.{pair}.cw")
        n.add(
            R.macro("CWP", tok(pair)), pval(v["p_one_sided"]), run, f"clark_west.{pair}.p_one_sided"
        )
    for pair, v in r["pooled"]["diebold_mariano"].items():
        n.add(R.macro("DM", tok(pair)), R.num(v["dm"], 2), run, f"diebold_mariano.{pair}.dm")
        n.add(R.macro("DMP", tok(pair)), pval(v["p"]), run, f"diebold_mariano.{pair}.p")

    # how much of the gain over Kaplan-Meier the mechanics explain
    c = {m: pm[m]["uno_c_strat"] for m in pm}
    share = (c["DIST"] - c["km"]) / (c["ABCDx"] - c["km"])
    n.add("MechShareDIST", R.num(100 * share, 0), run, "100 (C_DIST - C_km) / (C_ABCDx - C_km)")
    share_m = (c["M_flex"] - c["km"]) / (c["ABCDx"] - c["km"])
    n.add(
        "MechShareMFlex", R.num(100 * share_m, 0), run, "100 (C_M_flex - C_km) / (C_ABCDx - C_km)"
    )
    n.add("GainOverMFlex", R.num(c["ABCx"] - c["M_flex"], 3), run, "C_ABCx - C_M_flex")
    n.add("GainOverKM", R.num(c["ABCDx"] - c["km"], 3), run, "C_ABCDx - C_km")

    # per year
    py = r["per_year"]
    keys = ["M", "M_flex", "RW", "ABCx", "ABCDx", "gbm_ABCD", "rsf_ABCD", "nn_seq_ABCD"]
    rows = []
    for y in YEARS:
        v = py[str(y)]
        rows.append({"Year": str(y), **{k: R.num(v[k]["uno_c_strat"], 3) for k in keys}})
    t["tab_peryear"] = R.tabular(
        pd.DataFrame(rows),
        align="l" + "c" * len(keys),
        header=["Year"] + [rf"\texttt{{{R.escape(k)}}}" for k in keys],
    )
    for a, b in (
        ("ABCDx", "M"),
        ("ABCx", "M_flex"),
        ("ABCx", "RW"),
        ("ABCDx", "ABCx"),
        ("nn_seq_ABCD", "M"),
        ("M_flex", "RW"),
    ):
        w = sum(py[str(y)][a]["uno_c_strat"] > py[str(y)][b]["uno_c_strat"] for y in YEARS)
        n.add(R.macro("YearsAbove", tok(f"{a}-{b}")), R.integer(w), run, f"per_year C {a} > {b}")
    for m in ("ABCDx", "M", "M_flex", "RW"):
        vals = [py[str(y)][m]["uno_c_strat"] for y in YEARS]
        n.add(R.macro("YearMin", tok(m)), R.num(min(vals), 3), run, f"min per-year C {m}")
        n.add(R.macro("YearMax", tok(m)), R.num(max(vals), 3), run, f"max per-year C {m}")
    t["fig_peryear"] = fig_peryear(py)
    hyper(t, r)

    # calibration of the main model
    cal = {h: pm["ABCDx"][f"calibration_{h}d"] for h in (5, 10, 20)}
    t["fig_calibration"] = fig_calibration(cal)
    for h, v in cal.items():
        gap = np.abs(np.array(v["predicted"]) - np.array(v["observed"]))
        n.add(
            R.macro("CalMaxGap", R.DIGITS[h] if h < 10 else {10: "ten", 20: "twenty"}[h]),
            R.num(float(gap.max()), 3),
            run,
            f"ABCDx calibration_{h}d max |pred - obs|",
        )
        n.add(
            R.macro("CalTopObs", {5: "five", 10: "ten", 20: "twenty"}[h]),
            R.num(v["observed"][-1], 3),
            run,
            f"ABCDx calibration_{h}d top decile observed",
        )
        n.add(
            R.macro("CalBottomObs", {5: "five", 10: "ten", 20: "twenty"}[h]),
            R.num(v["observed"][0], 3),
            run,
            f"ABCDx calibration_{h}d bottom decile observed",
        )

    # sensitivities: bootstrap block length and censoring at the fold boundary
    sens = r["pooled"]["paired_block_sensitivity"]
    rows = []
    for pair in ("ABCDx-km", "ABCx-M_flex", "ABCx-RW", "ABCDx-ABCx", "M_s-DIST_s", "ABCx-M"):
        row = {
            "Comparison": rf"\texttt{{{R.escape(pair.split('-')[0])}}} $-$ "
            rf"\texttt{{{R.escape(pair.split('-')[1])}}}",
            "b20": yes(paired["improves"][pair]),
        }
        for b in ("40", "60"):
            ci = sens[b]["ci"]
            ok = ci[f"{pair}:uno_c"]["lo"] > 0 and ci[f"{pair}:ibs"]["hi"] < 0
            row[f"b{b}"] = yes(ok)
        rows.append(row)
    bc = r["pooled"]["paired_boundary_censoring"]["improves"]
    t["tab_blocks"] = R.tabular(
        pd.DataFrame(rows),
        align="lccc",
        header=["Comparison", "20 sessions", "40 sessions", "60 sessions"],
    )
    for pair, ok in bc.items():
        n.add(
            R.macro("Boundary", tok(pair.replace("boundary:", ""))),
            yes(ok),
            run,
            f"paired_boundary_censoring.improves.{pair}",
        )

    # slices of ABCDx - M
    rows = []
    for name, s in r["pooled"]["slices"].items():
        ci = s["paired"]["ci"]
        rows.append(
            {
                "Slice": SLICE_LABEL.get(name, name.replace("_", " ")),
                "n": R.integer(s["n"]),
                "CA": R.num(s["metrics"]["ABCDx"]["uno_c_strat"], 3),
                "CM": R.num(s["metrics"]["M"]["uno_c_strat"], 3),
                "dC": ci_c(ci["ABCDx-M:uno_c"]),
                "dIBS": ci_ibs(ci["ABCDx-M:ibs"]),
                "imp": yes(s["paired"]["improves"]["ABCDx-M"]),
                "km": yes(s["paired"]["improves"]["ABCDx-km"]),
            }
        )
    t["tab_slices"] = R.tabular(
        pd.DataFrame(rows),
        align="lrcccccc",
        header=[
            "Test rows",
            "Rows",
            r"C \texttt{ABCDx}",
            r"C \texttt{M}",
            r"$\Delta C$ vs \texttt{M}",
            r"$\Delta$IBS vs \texttt{M}",
            r"Beats \texttt{M}",
            "Beats KM",
        ],
    )
    n.add(
        "SlicesBeatKM",
        R.integer(sum(s["paired"]["improves"]["ABCDx-km"] for s in r["pooled"]["slices"].values())),
        run,
        "slices where ABCDx beats KM",
    )
    n.add("SlicesCount", R.integer(len(r["pooled"]["slices"])), run, "number of slices")

    # block E (bank rows)
    be = r["pooled"]["block_e"]
    rows = []
    for pair, ok in be["paired"]["improves"].items():
        a, b = pair.split("-", 1)
        a, variant = (a.split("@") + ["main"])[:2]
        rows.append(
            {
                "Variant": variant.replace("_", " "),
                "Comparison": pair_label(a, b),
                "dC": ci_c(be["paired"]["ci"][f"{pair}:uno_c"]),
                "dIBS": ci_ibs(be["paired"]["ci"][f"{pair}:ibs"]),
                "imp": yes(ok),
            }
        )
        n.add(R.macro("BE", tok(pair.replace("@", "_"))), yes(ok), run, f"block_e.improves.{pair}")
    t["tab_blocke"] = R.tabular(
        pd.DataFrame(rows),
        align="llccc",
        header=[
            "Variant",
            "Comparison",
            r"$\Delta C$ (95\% CI)",
            r"$\Delta$IBS (95\% CI)",
            "Improves",
        ],
    )
    for m, v in be["metrics"].items():
        if "@" in m:
            continue
        n.add(R.macro("BEC", tok(m)), R.num(v["uno_c_strat"], 3), run, f"block_e.metrics.{m}")
        n.add(R.macro("BEIBS", tok(m)), R.num(v["ibs_strat"], 4), run, f"block_e.metrics.{m}")

    # D-018 attribution (supporting information)
    a = r["pooled"]["attribution_d018"]
    rows = []
    for k, v in sorted(a["leave_one_out"].items(), key=lambda kv: -kv[1]["d_ibs"]):
        rows.append(
            {
                "Dropped": k.removeprefix("loo-"),
                "d": R.num(1e4 * v["d_ibs"], 2, signed=True),
                "ci": R.interval(1e4 * v["d_ibs_lo"], 1e4 * v["d_ibs_hi"], 2),
                "p": pval(v["p_ibs_holm"]),
                "inf": yes(v["informative"]),
            }
        )
    t["tab_attribution"] = R.tabular(
        pd.DataFrame(rows),
        align="lcccc",
        header=[
            r"Feature dropped from \texttt{ABCDx}",
            r"$\Delta$IBS $\times 10^4$",
            r"95\% CI $\times 10^4$",
            "Holm $p$",
            "Informative",
        ],
    )
    n.add(
        "AttribInformative",
        R.integer(sum(v["informative"] for v in a["leave_one_out"].values())),
        run,
        "attribution informative count",
    )
    n.add("AttribCount", R.integer(len(a["leave_one_out"])), run, "attribution features")
    n.add("AttribResamples", R.integer(a["ibs_resamples"]), run, "attribution ibs_resamples")

    # H3 shape: share of rows reversing within 5 sessions by distance group and age bucket
    sh = pd.DataFrame(r["rq3_shape"])
    piv = sh.pivot_table(index="age_bucket", columns="dist_group", values="share")
    order = ["1-5", "6-10", "11-20", "21-40", "41-80", ">80"]
    piv = piv.reindex(order)[["at_extreme", "near", "far"]]
    cnt = sh.pivot_table(index="age_bucket", columns="dist_group", values="n").reindex(order)
    rows = [
        {
            "Age": R.escape(ab),
            **{
                g: R.num(piv.loc[ab, g], 3) + rf" ({R.integer(cnt.loc[ab, g])})"
                for g in piv.columns
            },
        }
        for ab in order
    ]
    t["tab_shape"] = R.tabular(
        pd.DataFrame(rows),
        align="lccc",
        header=["Swing age (sessions)", "At the extreme", "Near", "Far"],
    )
    return r


def hyper(t: dict[str, str], r: dict) -> None:
    """Supporting information: grids (configs/main.yaml) and the values chosen per test year."""
    from collections import Counter

    grids = yaml.safe_load((paths.paper_dir(PAPER) / "configs" / "main.yaml").read_text())[
        "tuning_grids"
    ]

    def family(m: str) -> str:
        if m.startswith(("gbm", "M_flex")):
            return "gbm"
        for f in ("cox", "rsf", "nn"):
            if m.startswith(f):
                return f
        return "logit"

    alias = {"C": "inverse penalty"}  # not to be confused with the concordance index C

    def fmt(d: dict) -> str:
        return ", ".join(f"{alias.get(k, k)} {v:g}" for k, v in d.items())

    family_label = {"logit": "Logistic hazards", "gbm": "Boosted hazards", "cox": "Cox",
                    "rsf": "Random survival forests", "nn": "Neural hazards"}  # fmt: skip
    lines = [
        r"\begin{longtable}{@{}L{0.36\linewidth}L{0.58\linewidth}@{}}",
        r"\toprule",
        r"Model & Chosen setting (number of test years) \\",
        r"\midrule",
        r"\endhead",
    ]
    for k, fam in enumerate(family_label):
        members = [(m, lab) for m, _, lab in MODELS if m not in ("km", "RW") and family(m) == fam]
        if not members:
            continue
        grid = "; ".join(f"{alias.get(a, a)} " + "/".join(f"{x:g}" for x in v)
                         for a, v in grids[fam].items())  # fmt: skip
        if k:
            lines.append(r"\midrule")
        lines.append(rf"\multicolumn{{2}}{{@{{}}l}}{{\textbf{{{family_label[fam]}}}"
                     rf" \quad \textit{{grid: {R.escape(grid)}}}}} \\")  # fmt: skip
        for m, lab in members:
            c = Counter(fmt(r["chosen"][str(y)][m]) for y in YEARS)
            settings = r" \newline ".join(rf"{R.escape(a)} ({v})" for a, v in c.most_common())
            lines.append(rf"{lab} & {settings} \\ \addlinespace[7pt]")
    lines += [r"\bottomrule", r"\end{longtable}"]
    t["tab_hyper"] = "\n".join(lines) + "\n"


def fig_peryear(py: dict) -> str:
    """pgfplots body: per-year year-stratified C of the key models."""
    series = [
        ("M", "M", "mark=square*"),
        ("M_flex", "M\\_flex", "mark=diamond*"),
        ("RW", "RW", "mark=triangle*,dashed"),
        ("ABCDx", "ABCDx", "mark=*,thick"),
        ("nn_seq_ABCD", "neural (nn\\_seq\\_ABCD)", "mark=o"),
    ]
    lines = [
        r"\begin{tikzpicture}",
        r"\begin{axis}[width=0.95\linewidth,height=6.2cm,xlabel={Test year},"
        r"ylabel={Year-stratified $C$},xtick={2017,...,2026},"
        r"x tick label style={/pgf/number format/1000 sep={}},"
        r"legend style={at={(0.5,1.03)},anchor=south,legend columns=3,font=\small},"
        r"ymajorgrids,grid style={gray!25}]",
    ]
    for m, lab, style in series:
        pts = " ".join(f"({y},{py[str(y)][m]['uno_c_strat']:.4f})" for y in YEARS)
        lines.append(rf"\addplot+[{style}] coordinates {{{pts}}};")
        lines.append(rf"\addlegendentry{{\texttt{{{lab}}}}}")
    lines += [r"\end{axis}", r"\end{tikzpicture}"]
    return "\n".join(lines) + "\n"


def fig_calibration(cal: dict) -> str:
    """pgfplots body: decile calibration of ABCDx at 5, 10 and 20 sessions."""
    lines = [
        r"\begin{tikzpicture}",
        r"\begin{axis}[width=0.62\linewidth,height=0.62\linewidth,xmin=0,xmax=1,ymin=0,"
        r"ymax=1,xlabel={Predicted probability of reversal},"
        r"ylabel={Observed (Kaplan--Meier)},legend pos=south east,legend style={font=\small},"
        r"grid=major,grid style={gray!25}]",
        r"\addplot[gray,dashed,domain=0:1] {x}; \addlegendentry{perfect calibration}",
    ]
    styles = {5: "mark=*", 10: "mark=square*", 20: "mark=triangle*"}
    for h, v in cal.items():
        pts = " ".join(
            f"({p:.4f},{o:.4f})" for p, o in zip(v["predicted"], v["observed"], strict=True)
        )
        lines.append(rf"\addplot+[{styles[h]}] coordinates {{{pts}}};")
        lines.append(rf"\addlegendentry{{{h} sessions}}")
    lines += [r"\end{axis}", r"\end{tikzpicture}"]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ robustness over k


def k_robustness(
    n: R.Numbers, t: dict[str, str], runs: dict[str, R.Run], bts: dict[str, R.Run]
) -> None:
    rows = []
    for k in ("k1_5", "k2", "k3"):
        r = runs[k].json("metrics.json")
        if r["stop_checks"]["stop"]:
            raise R.ReportError(f"{k}: stop rule hit")
        pm, pi = r["pooled"]["metrics"], r["pooled"]["paired"]
        b = bts[k].json("metrics.json")["open"]["pooled"]
        sh = max(v["mean"] for v in r["stop_checks"]["shuffled"].values())
        n.add(
            R.macro(k, "ImprovesABCDxKm"),
            yes(pi["improves"]["ABCDx-km"]),
            runs[k],
            "improves ABCDx-km",
        )
        rows.append(
            {
                "k": K_LABEL[k],
                **{f"c_{m}": R.num(pm[m]["uno_c_strat"], 3) for m in ("km", "RW", "M", "ABCDx")},
                "dcm": ci_c(pi["ci"]["ABCDx-M:uno_c"]),
                "dim": ci_ibs(pi["ci"]["ABCDx-M:ibs"]),
                "imp": yes(pi["improves"]["ABCDx-M"]),
                "sh": R.num(sh, 3),
                "sm": R.num(b["model"]["sharpe"], 2),
                "sb": R.num(b["bh"]["sharpe"], 2),
            }
        )
        tk = R.macro(k)
        for m in ("km", "RW", "M", "ABCDx"):
            n.add(
                R.macro(tk, "C", tok(m)),
                R.num(pm[m]["uno_c_strat"], 3),
                runs[k],
                f"pooled.metrics.{m}.uno_c_strat",
            )
        n.add(R.macro(tk, "DCABCDxM"), ci_c(pi["ci"]["ABCDx-M:uno_c"]), runs[k], "ABCDx-M:uno_c")
        n.add(R.macro(tk, "DIBSABCDxM"), ci_ibs(pi["ci"]["ABCDx-M:ibs"]), runs[k], "ABCDx-M:ibs")
        n.add(R.macro(tk, "ImprovesABCDxM"), yes(pi["improves"]["ABCDx-M"]), runs[k], "improves")
        n.add(R.macro(tk, "ShuffledMax"), R.num(sh, 3), runs[k], "max shuffled mean")
        n.add(R.macro(tk, "SharpeModel"), R.num(b["model"]["sharpe"], 2), bts[k], "open.pooled")
        n.add(R.macro(tk, "SharpeMech"), R.num(b["mech"]["sharpe"], 2), bts[k], "open.pooled")
        n.add(R.macro(tk, "SharpeDC"), R.num(b["dc"]["sharpe"], 2), bts[k], "open.pooled")
        if "clark_west" in r["pooled"] and "ABCDx-M" in r["pooled"]["clark_west"]:
            n.add(
                R.macro(tk, "CWPABCDxM"),
                pval(r["pooled"]["clark_west"]["ABCDx-M"]["p_one_sided"]),
                runs[k],
                "clark_west.ABCDx-M",
            )
        n.add(
            R.macro(tk, "YearsAboveABCDxM"),
            R.integer(
                sum(
                    r["per_year"][str(y)]["ABCDx"]["uno_c_strat"]
                    > r["per_year"][str(y)]["M"]["uno_c_strat"]
                    for y in YEARS
                )
            ),
            runs[k],
            "per_year ABCDx > M",
        )
    t["tab_k"] = R.tabular(
        pd.DataFrame(rows),
        align="l" + "c" * 10,
        header=[
            "$k$",
            "KM",
            r"\texttt{RW}",
            r"\texttt{M}",
            r"\texttt{ABCDx}",
            r"$\Delta C$ vs \texttt{M}",
            r"$\Delta$IBS vs \texttt{M}",
            r"Beats \texttt{M}",
            "Shuffled",
            "Model",
            r"B\&H",
        ],
    )


# ------------------------------------------------------------------ trading test


def trading(n: R.Numbers, t: dict[str, str], run: R.Run) -> None:
    b = run.json("metrics.json")
    for ex in ("open", "close"):
        o = b[ex]
        E = R.macro("Bt", ex)
        n.add(R.macro(E, "HFiveSupported"), yes(o["h5_supported"]), run, f"{ex}.h5_supported")
        for s, _ in STRATEGIES:
            p = o["pooled"][s]
            n.add(R.macro(E, "Sharpe", s), R.num(p["sharpe"], 2), run, f"{ex}.pooled.{s}.sharpe")
            n.add(
                R.macro(E, "Ret", s),
                R.num(100 * p["ann_return"], 1),
                run,
                f"{ex}.pooled.{s}.ann_return x100",
            )
            n.add(
                R.macro(E, "MDD", s),
                R.num(100 * p["max_drawdown"], 1),
                run,
                f"{ex}.pooled.{s}.max_drawdown x100",
            )
            for c, w in (("0.2%", "Low"), ("0.8%", "High")):
                n.add(
                    R.macro(E, "Sharpe", s, w),
                    R.num(o["pooled"][f"{s}@{c}"]["sharpe"], 2),
                    run,
                    f"{ex}.pooled.{s}@{c}.sharpe",
                )
        for pair, v in o["sharpe_diffs"].items():
            n.add(
                R.macro(E, "SD", tok(pair)),
                R.interval(v["lo"], v["hi"], 2),
                run,
                f"{ex}.sharpe_diffs.{pair}",
            )
        for s in ("model", "mech"):
            n.add(R.macro(E, "DSR", s), R.num(o["dsr"][s]["dsr"], 2), run, f"{ex}.dsr.{s}.dsr")
            n.add(R.macro(E, "PSR", s), R.num(o["psr"][s], 2), run, f"{ex}.psr.{s}")
        n.add(R.macro(E, "DSRTrials"), R.integer(o["n_trials"]), run, f"{ex}.n_trials")
        for d in o["dsr_n"]:
            n.add(R.macro(E, "DSRN", str(d["n"])), R.num(d["dsr"], 2), run, f"{ex}.dsr_n.{d['n']}")
        for per, v in o["subperiod_sharpe"].items():
            for s in ("model", "bh"):
                n.add(
                    R.macro(E, "Sub", per, s),
                    R.num(v[s], 2),
                    run,
                    f"{ex}.subperiod_sharpe.{per}.{s}",
                )
        for s, v, w in [
            (s, v, w)
            for s in ("model", "dc", "bh")
            for v, w in (("skip_unknown_limits", "Skip"), ("fail_on_floor_close", "Floor"))
        ]:
            n.add(
                R.macro(E, "Sharpe", s, w),
                R.num(o["pooled"][f"{s}@{v}"]["sharpe"], 2),
                run,
                f"{ex}.pooled.{s}@{v}.sharpe",
            )
        trades = sum(f["strategies"]["model"]["trades"] for f in o["folds"].values())
        n.add(R.macro(E, "TradesModel"), R.integer(trades), run, f"{ex}.folds.*.model.trades")
    o, c = b["open"], b["close"]
    rows = []
    for s, lab in STRATEGIES:
        p = o["pooled"][s]
        rows.append(
            {
                "Strategy": lab,
                "ret": R.num(100 * p["ann_return"], 1),
                "sh": R.num(p["sharpe"], 2),
                "mdd": R.num(100 * p["max_drawdown"], 1),
                "lo": R.num(o["pooled"][f"{s}@0.2%"]["sharpe"], 2),
                "hi": R.num(o["pooled"][f"{s}@0.8%"]["sharpe"], 2),
                "cl": R.num(c["pooled"][s]["sharpe"], 2),
            }
        )
    t["tab_trading"] = R.tabular(
        pd.DataFrame(rows),
        align="lcccccc",
        header=[
            "Strategy",
            r"Return (\% p.a.)",
            "Sharpe",
            r"Max.\ drawdown (\%)",
            r"Sharpe, 0.2\%",
            r"Sharpe, 0.8\%",
            "Sharpe, close",
        ],
    )
    taus = sorted({f["tau"]["model"] for f in o["folds"].values()})
    n.add("BtTauMin", R.num(taus[0], 2), run, "open.folds.*.tau.model min")
    n.add("BtTauMax", R.num(taus[-1], 2), run, "open.folds.*.tau.model max")


# ------------------------------------------------------------------ in-sample tests (H2 signs, H4)


def insample(n: R.Numbers, t: dict[str, str], h2: R.Run, rq4: R.Run) -> None:
    h = h2.json("metrics.json")
    rows = []
    names = {
        "spx_ret_xdir": r"\relax S\&P 500 return $\times\,\delta$",
        "nasdaq_ret_xdir": r"\relax Nasdaq return $\times\,\delta$",
        "vix_chg_xdir": r"\relax VIX change $\times\,\delta$",
    }
    for k, v in h["signs"].items():
        ys = h["yearly_signs"][k]
        rows.append(
            {
                "Term": names[k],
                "pred": r"\relax $+$" if k.startswith("vix") else r"\relax $-$",
                "coef": R.num(v["coef"], 3, signed=True),
                "z": R.num(v["z"], 2),
                "p": pval(v["p"]),
                "holm": pval(v["p_holm"]),
                "sup": yes(v["supported"]),
                "yrs": f"{ys['predicted_sign_years']} of {ys['nonzero_years']}",
            }
        )
        tk = tok(k)
        n.add(R.macro("HTwoCoef", tk), R.num(v["coef"], 3, signed=True), h2, f"signs.{k}.coef")
        n.add(R.macro("HTwoP", tk), pval(v["p"]), h2, f"signs.{k}.p")
        n.add(R.macro("HTwoHolm", tk), pval(v["p_holm"]), h2, f"signs.{k}.p_holm")
        n.add(
            R.macro("HTwoYears", tk),
            R.integer(ys["predicted_sign_years"]),
            h2,
            f"yearly_signs.{k}.predicted_sign_years",
        )
        n.add(
            R.macro("HTwoNonzero", tk),
            R.integer(ys["nonzero_years"]),
            h2,
            f"yearly_signs.{k}.nonzero_years",
        )
        n.add(R.macro("HTwoBinomP", tk), pval(ys["binomial_p"]), h2, f"yearly_signs.{k}.binomial_p")
    t["tab_h2signs"] = R.tabular(
        pd.DataFrame(rows),
        align="lccccccc",
        header=[
            "Term",
            "Predicted",
            "Coefficient",
            "$z$",
            "One-sided $p$",
            "Holm $p$",
            "Supported",
            "Yearly fits with predicted sign",
        ],
    )
    bj = h["bank_joint"]
    n.add("HTwoBankWald", R.num(bj["date"]["wald"], 2), h2, "bank_joint.date.wald")
    n.add("HTwoBankDf", R.integer(bj["date"]["df"]), h2, "bank_joint.date.df")
    n.add("HTwoBankP", pval(bj["p"]), h2, "bank_joint.p")
    n.add("HTwoRows", R.integer(h["rows"]), h2, "rows")

    q = rq4.json("metrics.json")
    p = q["primary_single_index"]
    real = p["real"]
    n.add("HFourCoef", R.num(real["coef"], 3, signed=True), rq4, "primary_single_index.real.coef")
    n.add("HFourZ", R.num(real["z"], 2), rq4, "primary_single_index.real.z (conservative)")
    n.add("HFourP", pval(real["p"]), rq4, "primary_single_index.real.p")
    n.add("HFourPostRows", R.integer(real["post_rows"]), rq4, "real.post_rows")
    n.add("HFourRows", R.integer(real["rows"]), rq4, "real.rows")
    n.add("HFourRank", R.integer(p["rank_of_real"]), rq4, "rank_of_real")
    n.add("HFourPlacebos", R.integer(len(p["placebos"])), rq4, "number of placebos")
    n.add("HFourSupported", yes(p["h4_supported"]), rq4, "h4_supported")
    w = q["secondary_wald_10"]["real"]
    wp = max(w["date"]["p"], w["two_way"]["p"])
    n.add("HFourWaldP", pval(wp), rq4, "secondary_wald_10.real max(date, two_way) p")
    rows = [
        {
            "Window": r"Real (7 October 2025)",
            "coef": R.num(real["coef"], 3, signed=True),
            "z": R.num(real["z"], 2),
            "p": pval(real["p"]),
        }
    ]
    for y, v in p["placebos"].items():
        rows.append(
            {
                "Window": f"Placebo, 7 October {y}",
                "coef": R.num(v["coef"], 3, signed=True),
                "z": R.num(v["z"], 2),
                "p": pval(v["p"]),
            }
        )
    t["tab_rq4"] = R.tabular(
        pd.DataFrame(rows),
        align="lccc",
        header=["Announcement date", r"$\hat\lambda$", "$z$", "One-sided $p$"],
    )


# ------------------------------------------------------------------ sample and data facts


def _km(d: np.ndarray, e: np.ndarray, hs=(5, 10, 20)) -> dict[int, float]:
    s, out = 1.0, {}
    for x in range(1, max(hs) + 1):
        at_risk = (d >= x).sum()
        if at_risk:
            s *= 1 - ((d == x) & (e == 1)).sum() / at_risk
        if x in hs:
            out[x] = s
    return out


def sample(n: R.Numbers, t: dict[str, str], reg: dict) -> None:
    snap = reg["snapshot"]
    base = paths.SNAPSHOTS / snap
    labels = R.Run.load(PAPER, reg["labels"])
    feats = R.Run.load(PAPER, reg["features"])
    src = f"snapshot:{snap}"

    u = pd.read_parquet(base / "universe_daily.parquet")
    u["trade_date"] = pd.to_datetime(u.trade_date)
    for col in ("has_price", "in_vn30", "is_bank"):
        u[col] = u[col].astype(bool)
    u = u[(u.trade_date >= STUDY_START) & (u.trade_date <= STUDY_END)]
    pr = pd.read_parquet(
        base / "prices_raw.parquet", columns=["ticker", "trade_date", "n_prior_days"]
    )
    pr["trade_date"] = pd.to_datetime(pr.trade_date)
    u = u.merge(pr, on=["ticker", "trade_date"], how="left")
    ds = pd.read_parquet(
        feats.path / "dataset.parquet",
        columns=[
            "ticker",
            "trade_date",
            "event",
            "duration",
            "censor_reason",
            "direction",
            "in_vn30",
            "is_bank",
            "swing_age",
        ],
    )
    ds["trade_date"] = pd.to_datetime(ds.trade_date)
    for col in ("in_vn30", "is_bank"):
        ds[col] = ds[col].astype(bool)
    test = lambda df: df.trade_date >= TEST_START  # noqa: E731
    steps = [
        ("Universe stock-days (VN30 members and banks)", u),
        ("with a price that day", u[u.has_price]),
        ("with at least 250 prior sessions", u[u.has_price & (u.n_prior_days >= 250)]),
        ("inside an open swing (k = 2): survival rows", ds),
    ]
    rows = []
    for lab, df in steps:
        rows.append(
            {
                "Step": lab,
                "All": R.integer(len(df)),
                "Dev": R.integer((~test(df)).sum()),
                "Test": R.integer(test(df).sum()),
                "Banks": R.integer(df.is_bank.sum()),
                "VN": R.integer(df.in_vn30.sum()),
            }
        )
    st = ds.ticker.nunique()
    rows.append(
        {
            "Step": "Stocks with survival rows",
            "All": R.integer(st),
            "Dev": R.integer(ds[~test(ds)].ticker.nunique()),
            "Test": R.integer(ds[test(ds)].ticker.nunique()),
            "Banks": R.integer(ds[ds.is_bank].ticker.nunique()),
            "VN": R.integer(ds[ds.in_vn30].ticker.nunique()),
        }
    )
    t["tab_sample"] = R.tabular(
        pd.DataFrame(rows),
        align="lrrrrr",
        header=["Step", "All", "2012--2016", "2017--2026", "Banks", "VN30"],
    )
    n.add("SurvivalRows", R.integer(len(ds)), feats, "dataset.parquet rows")
    n.add("TestRows", R.integer(test(ds).sum()), feats, "dataset rows from 2017")
    n.add("DevRows", R.integer((~test(ds)).sum()), feats, "dataset rows before 2017")
    n.add("StockCount", R.integer(st), feats, "distinct tickers")
    n.add("UniverseStockDays", R.integer(len(u)), None, f"{src} universe_daily in study period")

    # descriptive statistics of swings and survival rows
    rev = pd.read_parquet(labels.path / "reversals_k2.parquet")
    rev = rev.sort_values(["ticker", "extreme_index"])
    rev["length"] = rev.groupby("ticker").extreme_index.diff()
    rev["lag"] = rev.confirm_index - rev.extreme_index
    rev["confirm_date"] = pd.to_datetime(rev.confirm_date)
    rev = rev[(rev.confirm_date >= STUDY_START) & (rev.confirm_date <= STUDY_END)]
    rows = []
    for d, lab in ((1, "Up-swings"), (-1, "Down-swings"), (0, "All")):
        sw = rev if d == 0 else rev[rev.ended_direction == d]
        rr = ds if d == 0 else ds[ds.direction == d]
        km = _km(rr.duration.to_numpy(), rr.event.to_numpy())
        rows.append(
            {
                "": lab,
                "sw": R.integer(len(sw)),
                "len": R.num(float(sw.length.median()), 0),
                "lag": R.num(float(sw.lag.median()), 0),
                "rows": R.integer(len(rr)),
                "cens": R.num(100 * (1 - rr.event.mean()), 1),
                "D": R.num(float(rr[rr.event == 1].duration.median()), 0),
                "s5": R.num(km[5], 3),
                "s10": R.num(km[10], 3),
                "s20": R.num(km[20], 3),
            }
        )
        if d == 0:
            n.add("SwingsConfirmed", R.integer(len(sw)), labels, "reversals_k2 in study period")
            n.add(
                "SwingLengthMedian",
                R.num(float(sw.length.median()), 0),
                labels,
                "median sessions between extremes",
            )
            n.add(
                "ConfirmLagMedian",
                R.num(float(sw.lag.median()), 0),
                labels,
                "median sessions extreme to confirmation",
            )
            n.add(
                "CensoredPct", R.num(100 * (1 - rr.event.mean()), 1), feats, "100 (1 - mean event)"
            )
            n.add(
                "DMedian",
                R.num(float(rr[rr.event == 1].duration.median()), 0),
                feats,
                "median duration, event rows",
            )
            for h in (5, 10, 20):
                n.add(
                    R.macro("KMSurv", {5: "five", 10: "ten", 20: "twenty"}[h]),
                    R.num(km[h], 3),
                    feats,
                    f"Kaplan-Meier S({h}) of survival rows",
                )
    t["tab_desc"] = R.tabular(
        pd.DataFrame(rows),
        align="lrrrrrrccc",
        header=[
            "",
            "Swings",
            "Length",
            "Lag",
            "Rows",
            r"Censored (\%)",
            "Median $D$",
            "$S(5)$",
            "$S(10)$",
            "$S(20)$",
        ],
    )
    cr = ds[ds.event == 0].censor_reason.value_counts()
    for k, v in cr.items():
        n.add(R.macro("Censored", k), R.integer(v), feats, f"censor_reason == {k}")
    n.add("UpRowsPct", R.num(100 * (ds.direction == 1).mean(), 1), feats, "share of up-swing rows")

    # data-section facts from the snapshot
    vn = pd.read_parquet(base / "vn30_membership.parquet")
    launch = vn.valid_from.min()
    n.add("VNThirtyStocks", R.integer(vn.ticker.nunique()), None, f"{src} vn30_membership tickers")
    n.add(
        "VNThirtyChanges",
        R.integer((vn.valid_from > launch).sum()),
        None,
        f"{src} vn30_membership spells starting after the launch",
    )
    seed = pd.read_csv(paths.SEEDS / "vn30_baskets.csv")
    n.add(
        "VNThirtyBaskets",
        R.integer(seed.effective_date.nunique()),
        None,
        "seed vn30_baskets.csv distinct basket dates",
    )
    bs = pd.read_parquet(base / "bank_spells.parquet")
    n.add("BankCount", R.integer(bs.ticker.nunique()), None, f"{src} bank_spells tickers")
    for col, name in (("in_vn30", "CoverageVNThirty"), ("is_bank", "CoverageBanks")):
        x = u[u[col]]
        n.add(
            name,
            R.num(100 * x.has_price.mean(), 1) + r"\%",
            None,
            f"{src} universe_daily has_price share, {col}",
        )
    lm = pd.read_parquet(base / "local_market.parquet")
    lm["trade_date"] = pd.to_datetime(lm.trade_date)
    lm = lm[(lm.trade_date >= STUDY_START) & (lm.trade_date <= STUDY_END)]
    n.add(
        "ForeignMissingSessions",
        R.integer(lm.foreign_net_value_vnd.isna().sum()),
        None,
        f"{src} local_market foreign_net_value_vnd missing",
    )
    be = pd.read_parquet(base / "block_e_npl.parquet")
    ok = be[be.npl_ratio.notna()]
    n.add("BlockECoverage", R.integer(len(ok)), None, f"{src} block_e_npl with npl_ratio")
    n.add("BlockEOCR", R.integer((ok.value_source == "ocr").sum()), None, f"{src} value_source ocr")
    n.add(
        "BlockEVisual",
        R.integer((ok.value_source == "visual").sum()),
        None,
        f"{src} value_source visual",
    )
    n.add("BlockEStatements", R.integer(len(be)), None, f"{src} block_e_npl rows")
    dev = [
        p.name
        for p in paths.runs_dir(PAPER).iterdir()
        if p.is_dir() and p.name < reg["dev_runs_before"]
    ]
    n.add("DevRunCount", R.integer(len(dev)), None, "run folders before the final snapshot")


def _md(text: str) -> str:
    """Markdown cell -> LaTeX text (bold and code marks dropped, special characters escaped)."""
    import re

    return R.escape(re.sub(r"\*\*|`", "", text).strip())


def records(n: R.Numbers, t: dict[str, str], reg: dict) -> None:
    """Supporting information: every development run (RUNS.md) and every design decision
    (DECISIONS.md), with its date."""
    import re

    dev = {p.name for p in paths.runs_dir(PAPER).iterdir()
           if p.is_dir() and p.name < reg["dev_runs_before"]}  # fmt: skip
    rows = []
    for line in (paths.runs_dir(PAPER) / "RUNS.md").read_text().splitlines():
        cells = [c for c in line.split("|")[1:-1]]
        if len(cells) < 5:
            continue
        name = cells[0].strip().strip("`")
        if name in dev:
            rows.append(
                {
                    "Run": r"\relax\nolinkurl{" + name + "}",  # breakable (xurl)
                    "What": r"\relax " + _md(cells[3]),
                    "Status": r"\relax " + _md(cells[4]),
                }
            )
    if {r["Run"] for r in rows} and len(rows) != len(dev):
        missing = dev - {re.sub(r".*nolinkurl\{|\}$", "", r["Run"]) for r in rows}
        raise R.ReportError(f"development runs missing from RUNS.md: {sorted(missing)}")
    # one block per run (a three-column table of long verbatim text is hard to read)
    blocks = []
    for i, r in enumerate(rows, 1):
        blocks.append(
            rf"\noindent\textbf{{{i}.}} {r['Run'].removeprefix(chr(92) + 'relax')}\\"
            + "\n"
            + rf"\textit{{Purpose:}} {r['What'].removeprefix(chr(92) + 'relax ')}\\"
            + "\n"
            + rf"\textit{{Outcome:}} {r['Status'].removeprefix(chr(92) + 'relax ')}\par\smallskip"
        )
    t["tab_devruns"] = "\n\n".join(blocks) + "\n"
    dec, text = [], (paths.paper_dir(PAPER) / "DECISIONS.md").read_text()
    for m in re.finditer(r"^## (D-\d{3}) — (.+?)$(.*?)(?=^## D-|\Z)", text, re.M | re.S):
        date = re.search(r"\*\*Date:\*\*\s*([0-9-]{10})", m.group(3))
        dec.append(
            {
                "Decision": m.group(1),
                "Date": date.group(1) if date else "",
                "Title": r"\relax " + _md(m.group(2)),
            }
        )
    body = R.tabular(pd.DataFrame(dec), align="lll", header=["Decision", "Date", "Subject"])
    t["tab_decisions"] = body.replace(
        "\\begin{tabular}{lll}", "\\begin{longtable}{llL{0.68\\linewidth}}"
    ).replace("\\end{tabular}", "\\end{longtable}")
    n.add("DecisionCount", R.integer(len(dec)), None, "DECISIONS.md entries")


def abolmakarem(n: R.Numbers, t: dict[str, str], run: R.Run) -> None:
    """Supporting information: their design on our development years (protocol 5d)."""
    m = run.json("metrics.json")
    res = m["results"]
    rows = []
    for how, hl in (("random", "Random"), ("chronological", "Chronological")):
        for al, alab in (("next", "next day (correct)"), ("same", "same day")):
            g = lambda k, how=how, al=al: res[f"{how}:{al}:{k}"]  # noqa: E731
            rows.append(
                {
                    "Split": hl,
                    "Target": alab,
                    "tr": R.num(g("trend")["accuracy"], 3),
                    "trb": R.num(g("trend")["majority_class"], 3),
                    "pk": R.num(g("pk")["accuracy"], 3),
                    "pkb": R.num(g("pk")["majority_class"], 3),
                    "r2": R.num(g("ret")["r2"], 4),
                }
            )
            for k, key in (("trend", "accuracy"), ("pk", "accuracy"), ("ret", "r2")):
                n.add(
                    R.macro("Abol", how, al, k),
                    R.num(g(k)[key], 3 if key == "accuracy" else 4),
                    run,
                    f"results.{how}:{al}:{k}.{key}",
                )
            n.add(
                R.macro("Abol", how, al, "TrendBase"),
                R.num(g("trend")["majority_class"], 3),
                run,
                f"results.{how}:{al}:trend.majority_class",
            )
            n.add(
                R.macro("Abol", how, al, "PkBase"),
                R.num(g("pk")["majority_class"], 3),
                run,
                f"results.{how}:{al}:pk.majority_class",
            )
    t["tab_abol"] = R.tabular(
        pd.DataFrame(rows),
        align="llccccc",
        header=[
            "Split",
            "Inputs of day $t$ predict the target of",
            "Trend: accuracy",
            "majority class",
            "Peak: accuracy",
            "majority class",
            r"Return: $R^2$",
        ],
    )
    n.add("AbolRows", R.integer(m["rows"]), run, "rows")
    n.add("AbolStocks", R.integer(m["stocks"]), run, "stocks")


SHAP_BLOCK_LABEL = {
    "A": "A. Swing state",
    "B": "B. Stock technicals",
    "C": "C. Local market",
    "D": "D. Global, overnight",
}


def shap_table(n: R.Numbers, t: dict[str, str], run: R.Run, top: int = 12) -> None:
    """Supporting information: descriptive SHAP for the 2026 models (protocol 5e)."""
    from vnbank.research.survival.final.shap_explain import BLOCKS

    m = run.json("metrics.json")
    cfg = run.config
    block_of = {c: b for b, cs in BLOCKS.items() for c in cs}
    rows = []
    for b, lab in SHAP_BLOCK_LABEL.items():
        rows.append(
            {
                "f": r"\relax\textit{" + lab + "}",
                "g": R.num(100 * m["gbm_ABCD"]["block_share"][b], 1),
                "nn": R.num(100 * m["nn_seq_ABCD"]["block_share"][b], 1),
            }
        )
        for key, mod in (("Gbm", "gbm_ABCD"), ("Nn", "nn_seq_ABCD")):
            n.add(
                R.macro("Shap", key, "Block", b),
                R.num(100 * m[mod]["block_share"][b], 1),
                run,
                f"{mod}.block_share.{b} x100",
            )
    t["tab_shap_blocks"] = R.tabular(
        pd.DataFrame(rows),
        align="lcc",
        header=["Feature block", r"Boosted hazard (\% of total)", r"Sequence neural (\% of total)"],
    )
    rank = {
        mod: sorted(m[mod]["mean_abs_shap"].items(), key=lambda kv: -kv[1])
        for mod in ("gbm_ABCD", "nn_seq_ABCD")
    }
    rows = []
    for i in range(top):
        row = {"r": str(i + 1)}
        for mod, k in (("gbm_ABCD", "g"), ("nn_seq_ABCD", "n")):
            f, v = rank[mod][i]
            d = m[mod]["direction_corr"].get(f)
            sign = "" if d is None else ("$+$" if d > 0 else "$-$")
            row[k] = rf"\relax\texttt{{{R.escape(f)}}} ({block_of[f]})"
            row[k + "v"] = R.num(100 * v, 2)
            row[k + "d"] = r"\relax " + sign if sign else r"\textemdash{}"
        rows.append(row)
    t["tab_shap_top"] = R.tabular(
        pd.DataFrame(rows),
        align="rlcclcc",
        header=[
            "Rank",
            "Boosted hazard",
            "Mean $|\\phi|$",
            "Dir.",
            "Sequence neural",
            "Mean $|\\phi|$",
            "Dir.",
        ],
    )
    for mod, key in (("gbm_ABCD", "Gbm"), ("nn_seq_ABCD", "Nn")):
        n.add(
            R.macro("Shap", key, "Additivity"),
            R.num(m[mod]["additivity_max_abs_error"], 6),
            run,
            f"{mod}.additivity_max_abs_error",
        )
        n.add(
            R.macro("Shap", key, "MeanPred"),
            R.num(m[mod]["mean_prediction"], 3),
            run,
            f"{mod}.mean_prediction",
        )
        f, v = rank[mod][0]
        n.add(
            R.macro("Shap", key, "TopShare"),
            R.num(100 * v / sum(x for _, x in rank[mod]), 1),
            run,
            f"{mod}: top feature share",
        )
    n.add("ShapRows", R.integer(cfg["rows"]), run, "config rows")
    n.add("ShapBackground", R.integer(cfg["background_rows"]), run, "config background_rows")


def main(argv: list[str] | None = None) -> int:
    reg = registry()
    n, t = R.Numbers(PAPER), {}
    ev = {k: R.Run.load(PAPER, v) for k, v in reg["evaluate"].items()}
    bt = {k: R.Run.load(PAPER, v) for k, v in reg["backtest"].items()}
    evaluation(n, t, ev["k2"])
    k_robustness(n, t, ev, bt)
    trading(n, t, bt["k2"])
    insample(n, t, R.Run.load(PAPER, reg["h2"]), R.Run.load(PAPER, reg["rq4"]))
    sample(n, t, reg)
    dc = R.Run.load(PAPER, reg["data_checks"])
    m = dc.json("metrics.json")
    o, b = m["cafef_overlap"], m["block_e_news"]
    if o["all_five_equal"] != o["overlap_days"]:
        raise R.ReportError("CafeF sources disagree on some overlap days; the text says they agree")
    n.add("PriceOverlapDays", R.integer(o["overlap_days"]), dc, "cafef_overlap.overlap_days")
    n.add("PriceOverlapTickers", R.integer(o["tickers"]), dc, "cafef_overlap.tickers")
    n.add(
        "BlockENewsMatched", R.integer(b["with_result_news"]), dc, "block_e_news.with_result_news"
    )
    n.add(
        "BlockENewsLead",
        R.integer(b["news_before_available"]),
        dc,
        "block_e_news.news_before_available",
    )
    n.add(
        "BlockENewsLeadDays", R.num(b["median_lead_days"], 0), dc, "block_e_news.median_lead_days"
    )
    records(n, t, reg)
    abolmakarem(n, t, R.Run.load(PAPER, reg["abolmakarem"]))
    if "shap" in reg:
        shap_table(n, t, R.Run.load(PAPER, reg["shap"]))
    n.add("SnapshotId", R.escape(reg["snapshot"]), None, "report.yaml snapshot")
    n.add("FinalCommit", R.escape(ev["k2"].commit[:7]), ev["k2"], "config git_commit")
    commit = code_version()
    p = n.write(OUT, "vnbank.research.survival.report", commit)
    for name, body in t.items():
        if name.startswith("fig_"):
            OUT.mkdir(parents=True, exist_ok=True)
            (OUT / f"{name}.tex").write_text(
                "% GENERATED FILE: do not edit by hand. Source: vnbank.research.survival.report\n"
                + body
            )
        else:
            R.write_table(OUT, name, body, "vnbank.research.survival.report")
    print(f"wrote {p} ({len(n.entries)} macros) and {len(t)} tables/figures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
