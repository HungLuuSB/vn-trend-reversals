"""D-023 timing validation: result-news matching on CafeF URL slugs."""

import pandas as pd

from vnbank.research.survival.features.block_e_timing import earliest_news, is_result_news

U = "https://cafef.vn/{}-20150420101010123.chn"


def test_result_news_needs_the_quarter_and_a_result_word():
    assert is_result_news(U.format("vietcombank-lai-truoc-thue-quy-1-tang-12"), 2015, 1)
    assert is_result_news(U.format("bidv-loi-nhuan-6-thang-dat-4000-ty"), 2015, 2)
    assert is_result_news(U.format("no-xau-acb-quy-iii-giam"), 2015, 3)
    assert is_result_news(U.format("mbbank-loi-nhuan-nam-2015-vuot-ke-hoach"), 2015, 4)
    assert not is_result_news(U.format("vietcombank-lai-truoc-thue-quy-2-tang"), 2015, 1)
    assert not is_result_news(U.format("vietcombank-dai-hoi-co-dong-quy-1"), 2015, 1)
    assert not is_result_news(U.format("quy-10-ty-lai"), 2015, 1)  # quy-10 is not quy-1


def test_earliest_news_is_inside_the_window_after_quarter_end():
    st = pd.DataFrame({"symbol": ["VCB"], "year": [2015], "q": [1]})
    t = lambda s: pd.Timestamp(s, tz="UTC")  # noqa: E731
    arts = pd.DataFrame({
        "ticker": ["VCB"] * 3,
        "published_at_utc": [t("2015-03-20"), t("2015-04-21"), t("2015-04-25")],
        "url": [U.format("vcb-loi-nhuan-quy-1-du-kien"), U.format("vcb-lai-quy-1-tang"),
                U.format("vcb-loi-nhuan-quy-1-2015")],
    })  # fmt: skip
    assert earliest_news(st, arts).iloc[0] == t("2015-04-21")  # before quarter end: ignored
