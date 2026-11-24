from research.dev_decompose import DIFFS, SPECS
from research.features.assemble import FEATURES_D


def test_specs_are_nested_and_exclude_global_block():
    names = list(SPECS)
    for small, big in zip(names, names[1:], strict=False):
        assert set(SPECS[small]) < set(SPECS[big])
    assert not set(SPECS["ABC"]) & set(FEATURES_D)
    assert all(a in SPECS and b in SPECS for a, b in DIFFS)
