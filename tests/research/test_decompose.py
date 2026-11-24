from research.dev_decompose import DIFFS, SPECS
from research.features.assemble import FEATURES_D


def test_specs_are_nested_and_exclude_global_block():
    names = list(SPECS)
    for small, big in zip(names, names[1:], strict=False):
        assert set(SPECS[small]) < set(SPECS[big])
    assert not set(SPECS["ABC"]) & set(FEATURES_D)
    assert all(a in SPECS and b in SPECS for a, b in DIFFS)


def test_d016_specs_build_on_the_mechanical_baseline():
    from research.dev_decompose import DIFFS_D016, SPECS_D016
    from research.features.assemble import FEATURES_A, FEATURES_MECH

    assert set(FEATURES_MECH) <= set(FEATURES_A)
    for name in ("MB", "MBC", "MD"):
        assert set(SPECS_D016["M"]) < set(SPECS_D016[name])
    assert set(SPECS_D016["MB"]) < set(SPECS_D016["MBC"])
    assert not set(SPECS_D016["MBC"]) & set(FEATURES_D)
    assert set(FEATURES_D) <= set(SPECS_D016["ABCD"])
    assert all(a in SPECS_D016 and b in SPECS_D016 for a, b in DIFFS_D016)
