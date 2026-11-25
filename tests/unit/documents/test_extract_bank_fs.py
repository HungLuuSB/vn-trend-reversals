def test_candidate_keys_follow_first_release_precedence():
    from vnbank.documents.extract_bank_fs import candidate_keys

    keys = [
        "cafef_filings/2026-11-25/VCB_22Q2_BCTC_HN.aaaa1111.pdf",
        "cafef_filings/2026-11-25/VCB_22Q2_BCTC_HN_2022-092134.bbbb2222.pdf",  # a version
        "cafef_filings/2026-11-25/VCB_22Q2_BCTC_HNSX.cccc3333.pdf",  # loses to HN
        "cafef_filings/2026-11-25/VCB_22Q2_BCTC_M.dddd4444.pdf",
        "cafef_filings/2026-11-25/VCB_22CN_BCTC_HNKT.eeee5555.pdf",  # Q4 stand-in
        "cafef_filings/2026-11-25/VCB_22Q3_BCTC_M.ffff6666.pdf",  # nothing consolidated
        "cafef_filings/2026-11-26/VCB_22Q3_BCTC_M.ffff6666.pdf",  # later copy, same name
        "cafef_filings/2026-11-25/VCB_22Q1_BCTC_HNSX.gggg7777.pdf",  # HNSX only stands in for Q2
        "cafef_filings/2026-11-25/list_VCB_2022.hhhh8888.json",
    ]
    got = [k.rsplit("/", 1)[-1].split(".")[0] for k in candidate_keys(keys)]
    assert sorted(got) == sorted(["VCB_22Q2_BCTC_HN", "VCB_22Q2_BCTC_HN_2022-092134",
                                  "VCB_22CN_BCTC_HNKT", "VCB_22Q3_BCTC_M"])  # fmt: skip
