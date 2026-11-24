# Block E (bank fundamentals, news counts): data feasibility scout (2026-11-25)

Small probes only: about 40 requests across CafeF, Vietstock, VnExpress, HOSE, GDELT and a few others, plus 4 sample PDFs and 2 GDELT 15-minute files kept in a scratch folder. Nothing was written to the raw layer and no code was committed. Each item is marked as **fact** (observed, with URL) or **judgement**. Anything not observed is marked unverified.

Scope: Paper 1, bank subsample. Development needs 2012–2016 for ACB, BID, CTG, EIB, MBB, NVB, SHB, STB and VCB. The full study runs 2012-01 to 2026-11 for about 27 banks.

## Recommended source per series (judgement)

| Series | Primary | Publication time (`available_at_utc`) | Gap / fallback |
| --- | --- | --- | --- |
| NPL ratio (groups 3–5 / total loans) | Note "Phân tích chất lượng nợ cho vay" in the **first-released** quarterly consolidated FS PDF (CafeF mirror of the issuer's filing). Needs OCR. | No source gives a posting date (see facts). Use a conservative rule until exchange posting times are obtained. | Bank's IR page or HOSE/HNX filing for missing quarters (e.g. NVB Q4/2012) |
| Loan growth, deposit growth, LDR | Same PDFs: balance-sheet lines for customer loans and customer deposits | Same as NPL | CafeF statement pages as a **cross-check only** (no date, unknown version) |
| ROA, ROE | Same PDFs: income statement plus balance sheet | Same as NPL | — |
| NIM | Same PDFs, approximated as net interest income / average interest-earning assets | Same as NPL | The earning-asset definition needs a decision |
| CAR | **Not quarterly** (see facts). Semi-annual Pillar 3 disclosures from 2020; before that, annual report or audited FS only (unverified) | Publication date of each report | Drop CAR from quarterly features, or use a semi-annual series from 2020 only |
| Daily news count per bank | CafeF article archive: per-5-day sitemaps back to 2012 and `datePublished` to the second (+07:00) | `datePublished` of each article | Cheaper but sparse: CafeF's symbol-tagged event list (timestamped to the minute, back to 2008) |
| News (robustness only) | GDELT Translingual GKG, Vietnamese sources, from 2015-02-19 | GDELT processing time (later than publication, so conservative) | None for 2012–2014 |

## Facts observed

**Financial-statement PDFs and dates**
- **CafeF filing list:** `https://cafef.vn/du-lieu/Ajax/PageNew/FileBCTC.ashx?Symbol=vcb&Type=1&Year=2013` returns JSON with period, title and PDF link. It has **no publication date**. (Re-checked 2026-11-25 by the main session: the `Symbol` parameter is case-sensitive in practice. `VCB` returns the list and `vcb` returns an empty list; no date field is present.) Each record's `id` is a MongoDB ObjectId whose timestamp decodes to 2023-03-02, which is the migration date, not the filing date.
  - Lists for VCB 2013, ACB 2015 and SHB 2016 include parent and consolidated FS for Q1–Q4 plus the audited annual FS.
  - For Q2 they also include **both** the unreviewed and the reviewed ("soát xét") version. Example: ACB Q2/2015 has `ACB_15Q2_BCTC_HN.pdf` and `ACB_15Q2_BCTC_HNSX.pdf`.
  - NVB 2012 has **no Q4** filing listed.
- **PDF host:** the links point to `cafefnew.mediacdn.vn` and return 404 (`File not found`). The same paths on `cafef1.mediacdn.vn/Images/Uploaded/DuLieuDownload/<year>/<file>` return the PDFs.
- **Sample PDFs (fact; small sample):**

  | Filing | Pages | Text layer | PDF CreationDate (+07) |
  | --- | --- | --- | --- |
  | NVB Q3/2012 consolidated | 23 | **none** (scanned) | 2012-10-30 09:30 |
  | VCB Q3/2013 consolidated | 48 | **none** (scanned; producer "Adobe PDF Scan Library") | 2013-11-14 15:48 |
  | ACB Q3/2015 consolidated | 32 | noisy OCR from the scanner | 2015-11-04 15:24 |
  | SHB Q1/2016 consolidated | 43 | noisy OCR from the scanner | created 2016-04-29, modified 2016-05-17 |

  In the noisy OCR, diacritics are garbled and digits are misread ("t32.277.545" for 132,277,545).
- **NPL is derivable from the quarterly notes.** The five-group loan-quality table was found in ACB Q3/2015 (p18) and SHB Q1/2016 (p16). SHB also prints its NPL ratio directly ("Tỷ lệ nợ xấu", 1.19% at 31/03/2016). The scanned VCB and NVB files could not be checked without OCR.
- **CAR not found** by keyword in the ACB and SHB quarterly FS. This is weak evidence, because the OCR text is noisy.
  - According to div.gov.vn, Circular 41/2016/TT-NHNN requires CAR disclosure **every 6 months**, compulsory from **2020-01-01** (https://div.gov.vn/nhung-quy-dinh-moi-cua-thong-tu-41-2016-tt-nhnn).
  - The CAR disclosure rules before 2020 are unverified.
- **CafeF statement pages** (e.g. `https://cafef.vn/du-lieu/bao-cao-tai-chinh-ngan-hang/ACB/bsheet/2015/3/0/0/bang-can-doi-ke-toan.chn`) give quarterly balance-sheet values.
  - ACB loans to customers: 131,021,258 million VND at Q3/2015 and 116,324,055 million at Q4/2014. Both match the Q3/2015 PDF, so this item was **not restated**.
  - The pages carry no publication date and no flag for the consolidated or parent statement, or for original versus restated values. No NPL line was seen on the statement pages.
- **CafeF company events** (`https://cafef.vn/du-lieu/Ajax/Events_RelatedNews_New.aspx?symbol=VCB&floorID=0&configID=0&PageIndex=N&PageSize=30&Type=2`) list symbol-tagged news and exchange notices with dd/mm/yyyy HH:MM. For VCB they run back to 2008 (page 55), about 1,650 items in total.
  - The page covering May–Oct 2013 had about 30 items, roughly 6 a month.
  - It showed "VCB: Báo cáo tình hình quản trị 6 tháng" (25/07/2013 14:24) but **no FS-posting item** for Q2/2013, so FS posting times are not reliably there.
- **HOSE** (`https://www.hsx.vn/`) is a JavaScript app. Its bundle references a JSON API (`api.hsx.vn/.../news/securities/<symbol>/<type>?startDate&endDate`). That would be the best source of FS posting timestamps for HOSE banks.
  - I did **not** query it: the probe was blocked by this session's permission policy as access to an undocumented API. It needs the user's decision.
  - HOSE robots.txt allows everything.
- **HNX (`hnx.vn`) and the SSC portal (`congbothongtin.ssc.gov.vn`)** gave connection failures from the laptop (HTTP 000) on 2026-11-25. Their archives are unverified.
- **Vietstock** (`https://finance.vietstock.vn/VCB/tai-tai-lieu.htm`): the document list loads by AJAX with an anti-forgery token. The site has Free and paid packages. robots.txt disallows `/export`. Its terms were not found (unverified).

**News**
- **CafeF**
  - robots.txt: `Allow: /`.
  - The sitemap index (`https://cafef.vn/sitemap.xml`, 788 entries) lists 5-day sitemaps back to 2016. Older ones also resolve: `sitemaps-2012-1-1-5.xml` has 529 URLs, and `sitemaps-2012-3-1-5.xml` has 538 URLs with titles (about 110–140 articles on weekdays).
  - Article pages carry `datePublished` with a +07:00 offset to the second (e.g. `2012-03-05T23:13:22+07:00`).
  - **The 17-digit number in the URL is not the publication time.** It uses a 12-hour clock (only hours 01–12 occur in 538 URLs) and is the creation time: ID `…20120302022128…` was published 2012-03-04 23:36.
  - Sitemap `lastmod` is 2015-01-09, a migration date.
  - Footer: "© Copyright 2007 - 2026 - Công ty Cổ phần VCCorp". No terms-of-use page was found from the article (unverified).
- **Bank names in CafeF titles are rare.** Over 5 days in March 2012 (538 titles): ACB 2, BIDV 1, VietinBank 2, MB 2, Navibank 1, SHB 1, Sacombank 0, Vietcombank 0, "ngân hàng" 22. Daily counts therefore need the **article body**, not titles.
- **VnExpress:** robots.txt allows general crawlers and blocks named scrapers (e.g. Scrapy). The sitemap index lists per-day article sitemaps for 2001–2026, but every one tried (2012, 2016, 2025 and 2026-11-24) returned **302 to the homepage**. Not usable as probed.
- **Tin nhanh chứng khoán:** robots.txt disallows `/search/`, `/tim-kiem/` and `/api/`.
- **NDH:** a WordPress sitemap exists; robots.txt disallows `/api/`. Its archive depth is unverified.
- **GDELT**
  - Translingual covers Vietnamese (one of 65 languages; launch post dated 2015-02-19, https://blog.gdeltproject.org/?p=1369).
  - The translation file list (`https://data.gdeltproject.org/gdeltv2/masterfilelist-translation.txt`, 142 MB) starts at `20150218224500`.
  - Two 15-minute translation GKG files:

    | File | Rows | Vietnamese-language rows | Mentions of the 9 banks |
    | --- | --- | --- | --- |
    | 2016-03-15 02:15 UTC | 3,725 | 112 (baomoi, vietbao, giaoducthoidai, vietstock, zing, …) | **0** |
    | 2026-11-24 02:15 UTC | 1,202 | 66 | **0** |

  - CafeF was not among the top sources.
  - Files are 5–13 MB zipped per 15 minutes.
  - No Vietnamese coverage before 2015 (judgement: GDELT 1.0 GKG is English-only; unverified).

## Design issues to settle in `research/paper1/DECISIONS.md` before any data work (judgement)

1. **Publication time of filings (the core point-in-time problem).** No source probed gives the posting time of a quarterly FS.
   - Options:
     - (a) Ask the user to approve HOSE's API (and find HNX/SSC equivalents) for exact posting times.
     - (b) A conservative rule: `available_at` = max(statutory deadline, PDF CreationDate) + 1 session.
   - Rule (b) still breaks for late filers. The deadlines (Circular 52/2012, then 155/2015) are **unverified** and must be checked against the legal text.
   - Measure how often rule (b) differs from the true posting time on the subset where both are known.
2. **First release versus restated.**
   - **Q2:** use the unreviewed Q2 file, not the "soát xét" one.
   - **Year end:** use the unaudited Q4 file, not the audited annual FS.
   - **Comparatives:** never take prior-period figures from a later filing.
   - Aggregator values (CafeF, Vietstock, vnstock) carry no version or date, so they serve as cross-checks only.
3. **Consolidated or parent.** Fix one (consolidated is the natural choice) and fall back to parent only when no consolidated file exists, with a flag on the row.
4. **PDF effort.** 2 of 4 samples (2012, 2013) have no text, and the other 2 have unusable OCR. Plan to re-OCR all 2012–2016 files (Tesseract `vie` or similar), extract about 3 pages per filing, and validate with accounting identities: loan groups 1–5 sum to total loans, and the balance sheet balances.
   - Each extracted number is checked by hand on a sample. Whether later years have clean text layers is unverified.
5. **CAR.** It is not quarterly, and it is compulsory semi-annually only from 2020. Either drop it or define a semi-annual feature from 2020, with its own publication dates.
6. **NIM definition.** Decide on the earning-asset definition and on average versus end-of-period balances.
7. **News-count definition.**
   - Choose between the source universe options: CafeF only (archive back to 2012), or CafeF's curated symbol-tagged list (sparse).
   - Count on the body text (the alias list per bank, e.g. "Vietcombank/VCB/Ngoại thương", is a hand-checked seed).
   - Count only articles whose `datePublished` is before 09:00 on day t+1.
   - Single-source counts reflect CafeF's editorial mix; state this as a limitation.
   - GDELT is too sparse for bank-day counts and starts in 2015. Use it at most as a 2015+ robustness check, or skip it.
8. **Licensing and data rule 1 (needs the user).**
   - Filings are statutory public disclosures; mirroring them from CafeF is low risk.
   - Storing full article HTML in the raw layer (required by rule 1) copies VCCorp content. Ask CafeF/VCCorp for permission for academic use, or agree to store pages privately and publish only counts.
   - A CafeF crawl of about 700k article pages (about 130 a day × about 5,400 days) is a job of more than an hour, so it needs approval.
   - Paid alternatives (FiinPro, CEIC, Refinitiv) may have NPL or CAR series; their point-in-time vintages are unverified and they need credentials.
9. **Coverage gaps.** Missing quarters exist (NVB Q4/2012). Publish a bank × quarter coverage table before modelling. NVB, EIB and STB went through restructuring and mergers in the period, so expect gaps.

## Effort estimate (judgement)

- **Development, fundamentals** (9 banks × 20 quarters, about 200 PDFs including Q2 duplicates): download and catalogue 1 day; OCR and page finding 3–5 days; extraction with identity checks and a hand-checked sample 4–6 days; publication-time rule and its validation 2–3 days. **About 2–3 weeks.**
- **Full period, fundamentals** (about 27 banks × about 59 quarters, about 1,600–1,800 PDFs): **3–5 more weeks**. Less if post-2017 PDFs have clean text (unverified).
- **News counts:**
  - **Option 1, CafeF symbol-tagged list:** about 2,000 requests, **1–2 days**, but sparse and curated.
  - **Option 2, full CafeF body-text counts:** about 1,100 sitemaps plus about 700k pages. Roughly **2–3 weeks of polite crawling** (1 request per 2 s) plus 3–4 days of work on aliases and validation. It needs licensing clearance and job approval first.
