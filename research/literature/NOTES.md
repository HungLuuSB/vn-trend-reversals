# Reading notes: US factors and Vietnamese stocks (2026-11-25)

These are critical notes on the papers in this folder. Each paper was read in full. The key numbers below were checked against the extracted text (table rows cited); the full PDF text is not stored in the repo. The citations are checked as CLAUDE.md requires:
- **DOI verified:** the DOI resolves to the same paper.
- **Unverified:** no DOI is printed in the paper, and none is guessed.

## Synthesis: what the evidence says about "US factors move Vietnamese stocks"

**The published evidence is thin and weakly identified.** None of the three Vietnam papers combines:
- daily, point-in-time data;
- an out-of-sample test;
- coverage after 2018, when foreign participation and the market-upgrade process changed the market.

The two firm-panel papers are annual. Their US variable is the same for every firm, so the "effect" is identified from 7–9 yearly values with no year effects. Their controls are contemporaneous, including year-end accounting data that becomes public months later. The daily paper (Thuan 2011) covers 2003–2009 and finds its effects only in crisis-era sub-periods chosen after the fact.

**What looks real:** the previous US close carries information for the *next Vietnamese open* (Thuan 2011, a coefficient of about 0.2 in 2008–09). That is the opening gap: the US move is priced at the open. Our Paper 1 decision time (09:00, before the open) and our 2012–2016 development results are consistent with this. Daily US and global series do not help predict *when a swing reverses* (Findings 12, 15–17, 20). The two questions are different and both answers can be true.

**The gap this leaves (a possible Paper 3, not yet approved):** a pre-registered daily study, 2012–2026, that would:
1. split the Vietnamese return into the overnight gap and the open-to-close return, and test whether US information is fully absorbed at the open;
2. test formally whether the link changed after 2018 (break tests, regime interactions), instead of choosing breaks from events after the fact;
3. use *surprises* (FOMC rate surprises, VIX innovations, overnight S&P returns), not levels such as the Fed funds rate;
4. test the mechanism the 2025 paper only asserts: does US uncertainty predict foreign net flows on HOSE?
5. compare state-owned banks (VCB, BID, CTG) with private banks, and large firms with small ones.

Constraint: these tests use the same US series as Paper 1's final run. They would be run after that run, or on 2012–2016 only until then.

## Vo & Nguyen (2016): US monetary policy and Vietnamese stocks

Vo, X.V. & Nguyen, P.C. (2016). Impacts of the US monetary policy on the Vietnamese stock market. *Afro-Asian Journal of Finance and Accounting* 6(2), 119–134. **No DOI in the text: unverified.** File: `monetary/`.

- **Data:** annual returns of HOSE and HNX firms, 2006–2013 (the text also says 2005–2013); 2,168 firm-years. US policy is measured by the *level* of the Fed funds rate (FFR).
- **Method:** pooled OLS and firm fixed effects, with FFR × size, market-to-book and leverage interactions. All regressors are contemporaneous.
- **Findings:**
  - FFR alone is **not significant**: OLS −7.8573 (p = 0.331); FE −4.8303 and −11.9077 (p > 0.5) (Tables 4, 6).
  - FFR is marginal in the big-firm half only: −71.4278 (p = 0.054, Table 5).
  - The S&P 500 annual return enters *negatively*: −2.0164 (p = 0.007, Table 4).
  - The interactions are significant.
- **Weaknesses:**
  - The FFR level is not a policy shock.
  - Macro variables vary over about 7 years and errors are not clustered by year.
  - "Dynamic panel" is claimed, but no GMM is used, so there is Nickell bias.
  - There is look-ahead: market-to-book and year-end accounting data are used for the same year's return.
  - Returns are not winsorised (maximum 2,955%).
- **For us:** this is background only, not support. The heterogeneity idea (large, foreign-held stocks are more exposed) is worth testing properly with daily surprises.

## Thuan (2011): the US and Vietnam stock markets

Luu Tien Thuan (2011). The relationship between the United States and Vietnam stock markets. *International Journal of Business and Finance Research* 5(1), 77–89. **No DOI in the text: unverified.** File: `us-vn-spillover/`.

- **Data:** daily, December 2003 to August 2009, 1,482 returns. The VN-Index *opening* price is regressed on the previous S&P 500 or Dow Jones close. Quote: "the U.S. stock market closes at 3 AM (Vietnamese time) and the Vietnam Stock market opens at 8:30 AM" (it ignores US daylight saving time).
- **Method:** ARMA–GARCH(1,1) and EGARCH, with the lagged US return in the mean and squared US residuals in the variance. Sub-periods are cut at leaders' visits (2005, 2007, 2008).
- **Findings** (Table 6, lagged S&P coefficient, GARCH / EGARCH):

  | Period | GARCH | EGARCH |
  |---|---|---|
  | 2003–05 | −0.0841** | 0.0244 |
  | 2005–07 | 0.0543 | 0.0845 |
  | 2007–08 | 0.1402** | 0.1439** |
  | 2008–09 | 0.2589*** | 0.2627*** |

  There is **no volatility spillover**. The Dow Jones results are similar.
- **Weaknesses:**
  - No full-sample estimate and no standard errors, only stars.
  - Breaks are chosen from events after the fact, and the model is re-selected in each sub-period.
  - The rising effect coincides with the 2007 bubble and the 2008–09 crisis, when correlations rise with volatility.
  - Price limits are ignored, and there is no out-of-sample test.
- **For us:** the timing logic matches our 09:00 rule. We would replicate and extend it on 2012–2026 data:
  - zoneinfo-correct alignment;
  - the gap split from open-to-close;
  - several US lags, to allow for limit-capped moves;
  - formal break tests.

## Nguyen, Bao & Le (2025): US uncertainty and Vietnamese returns

Nguyen, T.H.P., Bao, H.H.G. & Le, H.P. (2025). US economic and political instability and Vietnamese stock returns: the roles of firm size and government ownership. *Cogent Economics & Finance* 13(1), 2584624. **DOI 10.1080/23322039.2025.2584624: verified.** File: `geopolitical/`.

- **Data:** 380 HOSE firms, annual, 2014–2023. The US measure is the World Uncertainty Index for the US (WUI; quarterly, and the annual aggregation is not described), lagged one year. No EPU, VIX or GPR series is used.
- **Method:** system GMM with US × size and US × state-ownership interactions. Firm and macro controls are contemporaneous.
- **Findings:**
  - US_{t−1} is *positive*: 6.126, 4.898, 0.531 and 6.546 across four return definitions (Table 5). The authors had predicted a negative sign.
  - In Table 6, US = 51.284 and US × SIZE = −3.036.
  - The effect is weaker for state-owned firms (Table 7).
  - The authors explain the result as "flight to emerging markets", but show no flow data.
- **Weaknesses:**
  - The US effect rests on about 9 annual values, with no year effects.
  - The instrument count is not reported, and the Hansen p-values are near 0.9.
  - The predicted sign was reversed after the results.
  - The four return measures are near-duplicates (RT1 and RT4 correlate at 0.94).
- **For us:** this does not contradict our daily nulls: frequency, measure and estimand all differ. Its claimed mechanism (US uncertainty leads to foreign inflows to Vietnam) is directly testable with daily foreign net flows. The state-ownership split fits our bank sample.

## Abolmakarem et al. (2024): multi-stage ML stock prediction (methods)

Abolmakarem, S., Abdi, F., Khalili-Damghani, K. & Didehkhani, H. (2024). A multi-stage machine learning approach for stock price prediction: engineered and derivative indices. *Intelligent Systems with Applications* 24, 200449. **DOI 10.1016/j.iswa.2024.200449: verified.** File: `methods/`.

- **Data and task:** four stocks (BP, BHP, GSK, VOD), daily, 2000–2020. The paper calls them FTSE 100 stocks, but the prices fit the NYSE ADRs. Targets are next-day direction, returns, turning points and price changes. The model is an MLP, compared with an LSTM.
- **Reported results:**
  - Next-day direction accuracy 95.8–97.0% (Table 8).
  - Test R² for returns 0.9999 (Table 26 area; e.g. BP 0.99992).
- **Audit:** these numbers are far above our red-flag thresholds (60% direction accuracy, R² of a few percent on daily returns). Likely causes:
  - a target/feature misalignment;
  - the MLP's 70/15/15 split, which is not stated as chronological;
  - full-sample min/max in some targets;
  - price-level inputs against price-level targets.
  - Internally, peak accuracy (about 75%) cannot be that low if direction is 97% predictable.
  - There is no naive baseline, no costs and no trading test.
- **For us:**
  - A list of practices our pipeline already guards against.
  - Usable, point-in-time features: intraday range ratios (ln H/O, ln L/O) and price-normalised ATR, RSI and ADX through the close of day t.
  - Cite only as an example of an evaluation pitfall, if at all.
