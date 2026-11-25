import pandas as pd


def test_candidate_keys_follow_first_release_precedence():
    from vnbank.documents.extract_bank_fs import candidate_keys, parse_name

    keys = [
        "cafef_filings/2026-11-25/VCB_22Q2_BCTC_HN.aaaa1111.pdf",
        "cafef_filings/2026-11-25/VCB_22Q2_BCTC_HN_2022-092134.bbbb2222.pdf",  # a version
        "cafef_filings/2026-11-25/VCB_22Q2_BCTC_HNSX.cccc3333.pdf",  # loses to HN
        "cafef_filings/2026-11-25/VCB_22Q2_BCTC_M.dddd4444.pdf",
        "cafef_filings/2026-11-25/VCB_22CN_BCTC_HNKT.eeee5555.pdf",  # Q4 stand-in
        "cafef_filings/2026-11-25/VCB_22Q3_BCTC_M.ffff6666.pdf",  # nothing consolidated
        "cafef_filings/2026-11-26/VCB_22Q3_BCTC_M.ffff6666.pdf",  # later copy, same name
        "cafef_filings/2026-11-25/VCB_22Q1_BCTC_HNSX.gggg7777.pdf",  # HNSX only stands in for Q2
    ]
    index = pd.DataFrame([{**parse_name(k.rsplit("/", 1)[-1]), "raw_key": k,
                           "name": k.rsplit("/", 1)[-1].split(".")[0]} for k in keys])  # fmt: skip
    # a single-entity bank (clarification 5): Q beats its reviewed SX stand-in and M
    index = pd.concat([index, pd.DataFrame([
        {"symbol": "LPB", "year": 2024, "period": "Q2", "kind": k, "suffix": n, "raw_key": n,
         "name": n} for k, n in (("Q", "lpb-q2"), ("SX", "lpb-sx"), ("M", "lpb-m"))])])  # fmt: skip
    got = [k.rsplit("/", 1)[-1].split(".")[0] for k in candidate_keys(index)]
    assert sorted(got) == sorted(["VCB_22Q2_BCTC_HN", "VCB_22Q2_BCTC_HN_2022-092134",
                                  "VCB_22CN_BCTC_HNKT", "VCB_22Q3_BCTC_M", "lpb-q2"])  # fmt: skip


def test_kind_from_description():
    from vnbank.documents.extract_bank_fs import kind_from_description as k

    assert k("Báo cáo tài chính hợp nhất quý 4 năm 2025") == "HN"
    assert k("Báo cáo tài chính hợp nhất quý 2 năm 2024 (đã soát xét)") == "HNSX"
    assert k("Báo cáo tài chính hợp nhất năm 2023 (đã kiểm toán)") == "HNKT"
    assert k("Báo cáo tài chính công ty mẹ quý 4 năm 2025") == "M"
    assert k("Báo cáo tài chính công ty mẹ năm 2023 (đã kiểm toán)") == "MKT"
    assert k("Báo cáo tài chính quý 1 năm 2026") == "Q"
    assert k("Báo cáo tài chính năm 2019 (đã kiểm toán)") == "KT"


def test_filing_index_handles_dotted_names_and_list_descriptions():
    import json

    from vnbank.common.raw_store import InMemoryRawStore
    from vnbank.documents.extract_bank_fs import filing_index

    store = InMemoryRawStore()
    fn = "20251026_-_MBB_-_BCTC_Hop_nhat_Q3.2025_viet_1761554111.pdf"
    lst = {"Data": [{"Time": "Q3/2025", "Name": "Báo cáo tài chính hợp nhất quý 3 năm 2025",
                     "Link": f"https://cafefnew.mediacdn.vn/x/{fn}"}], "Success": True}  # fmt: skip
    store.put_immutable("cafef_filings/2026-11-25/list_MBB_2025.0011aabb.json",
                        json.dumps(lst).encode(), {})  # fmt: skip
    store.put_immutable(f"cafef_filings/2026-11-25/{fn[:-4]}.0526fe86.pdf", b"%PDF", {})
    store.put_immutable("cafef_filings/2026-11-25/VCB_22Q2_BCTC_HN.aaaa1111.pdf", b"%PDF", {})
    ix = filing_index(store).set_index("symbol")
    assert ix.loc["MBB", "kind"] == "HN" and ix.loc["MBB", "period"] == "Q3"
    assert ix.loc["MBB", "kind_source"] == "list_name" and ix.loc["MBB", "year"] == 2025
    assert ix.loc["VCB", "kind_source"] == "filename"


def test_original_name_inverts_raw_key():
    from datetime import UTC, datetime

    from vnbank.common.raw_store import raw_key
    from vnbank.documents.extract_bank_fs import original_name

    t = datetime(2026, 11, 25, tzinfo=UTC)
    for fn in ("VCB_22Q2_BCTC_HN.pdf", "20251026_-_MBB_-_BCTC_Hop_nhat_Q3.2025_viet_17615.pdf",
               "000000014462963_VI_ABB_BCTC_Q4_06022025092424.2024_HN",
               "x_Q3.2025_ab.pdf?v=1786609107953", "nodot"):  # fmt: skip
        stored = raw_key("cafef_filings", t, fn, "0526fe86" + "0" * 56).rsplit("/", 1)[-1]
        assert original_name(stored, {fn}) == fn
