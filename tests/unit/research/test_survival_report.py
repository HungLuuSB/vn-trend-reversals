"""Helpers of the Paper 1 numbers builder (vnbank.research.survival.report)."""

import numpy as np

from vnbank.research.survival import report as P


def test_model_tokens_are_letters_only_and_distinct():
    toks = [P.tok(m) for m, _, _ in P.MODELS]
    assert all(t.isalpha() for t in toks)
    assert len(set(toks)) == len(toks)
    assert P.tok("nn_seq_ABCD-M") == "NnSeqABCDM"
    assert P.tok("M_s-DIST_s") == "MSDISTS"


def test_pval_floor_and_format():
    assert P.pval(0.0) == r"\ensuremath{<0.001}"
    assert P.pval(0.0441) == r"\ensuremath{0.044}"


def test_kaplan_meier_hand_computed():
    # durations 1,2,2,3 (all events) and 2 (censored): S(1)=4/5, S(2)=4/5*(1-2/4)=0.4,
    # S(3)=0.4*(1-1/1)=0
    d = np.array([1, 2, 2, 3, 2])
    e = np.array([1, 1, 1, 1, 0])
    s = P._km(d, e, hs=(1, 2, 3))
    assert s[1] == 0.8
    assert abs(s[2] - 0.4) < 1e-12
    assert s[3] == 0.0
