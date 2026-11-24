import pandas as pd

from vnbank.research.survival.aging import dist_groups


def test_dist_groups_at_extreme_and_median_split():
    d = pd.Series([0.0, 0.0, -0.1, -0.2, -0.8, -1.0])
    g = list(dist_groups(d))
    assert g == ["at_extreme", "at_extreme", "near", "near", "far", "far"]
