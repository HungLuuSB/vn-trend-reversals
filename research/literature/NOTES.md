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
5. compare state-owned banks (VCB, BID, CTG) with private banks, and large firms with small ones;
6. test whether US effects appear **only in crashes** (left-tail dependence between the US close on day t−1 and Vietnam on day t; a "US crash" indicator in the hazard model, with expanding-window thresholds; 2–3-day Vietnamese returns to catch moves capped by price limits). Nguyen, Bhatti & Henry (2017) suggest this, but they measure it on same-date pairs.

Paper 1's development data cannot be used for item 6 either: the D-017 guard closed block-D specifications there. Each item would be pre-registered for the final run or for Paper 3. Power is low: the bottom 1% of about 1,250 sessions in 2012–2016 is only about 12 events.

Constraint: these tests use the same US series as Paper 1's final run. They would be run after that run, or on 2012–2016 only until then.

## What the core literature adds (2026-11-25): a design, not just a gap

The five core papers below give the possible Paper 3 a concrete method for each weakness found in the Vietnam papers:

| Weakness in the Vietnam papers | Fix from the core literature |
|---|---|
| Same-date or open-to-open pairing; the US move may be priced at the open | **Hamao, Masulis & Ng (1990)**: split the domestic return into the overnight gap (close t−1 → open t) and open-to-close t. Regress each on the foreign open-to-close return of the market that traded last (US t−1). Treat a stale open as an artefact: it creates a spurious intraday mean effect. |
| "Stronger link after the crisis" read from correlations | **Forbes & Rigobon (2002)**: correlations rise mechanically with volatility; the regression slope does not (their eq. 5). Compare betas with regime interactions. Fix regimes from US-side events in advance, never from Vietnamese volatility. Control for common shocks. |
| The Fed funds rate *level* as the policy measure | **Bauer & Swanson (2023)**: narrow-window FOMC surprises, purged of public information released before the announcement. Raw surprises are fine for asset-price event studies; local projections need the purged series. |
| No mechanism | **Miranda-Agrippino & Rey (2020)**: a US tightening raises global risk aversion and cuts global banks' leverage, cross-border flows and risky asset prices. Testable daily chain: FOMC surprise → VIX or dollar → foreign net flows on HOSE → VN30 and bank returns. |
| Ad hoc uncertainty measures | **Baker, Bloom & Davis (2016)**: the US EPU index. The daily version exists but is revised and rescaled, so archived vintages are needed for any point-in-time use. |

**Data blockers** (to settle before pre-registering):
- **FOMC surprises end in June 2019** in Bauer & Swanson. Extending them to 2026 needs intraday federal funds and SOFR futures, which are usually paid data. First check whether their openICPSR package (doi 10.3886/E181661V1) or the purged series in their *NBER Macroeconomics Annual* follow-up (not yet read) goes further.
- **Foreign net flows on HOSE** are not collected yet.
- **HOSE opening-auction quality:** flag opens with no auction trade and opens at a price limit.

**Power:** about 8 FOMC meetings a year gives about 120 events in 2012–2026. From 2012 to 2015 the funds rate was at the zero lower bound, so the signal there sits in the path factor.

**For Paper 1 (interpretation only, no change):** Hamao et al. and Thuan imply that overnight US information is priced at the Vietnamese open. Paper 1 decides at 09:00, before the open, but its outcome (when a swing reverses) unfolds over days. A null for US series on reversal timing is therefore consistent with US information being absorbed at the open. That is a discussion point for the paper, not a new test on development data.

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

## Nguyen, Bhatti & Henry (2017): US contagion into Vietnam and China in extreme events

Nguyen, C., Bhatti, M.I. & Henry, D. (2017). Are Vietnam and Chinese stock markets out of the US contagion effect in extreme events? *Physica A*. **DOI 10.1016/j.physa.2017.02.045: verified.** The text is the accepted manuscript, so volume and pages must be taken from the published version before citing. File: `us-vn-spillover/`.

- **Data:** daily VN-Index, Shanghai, Shenzhen and S&P 500 (DataStream), 2003–2011. The start date is given three different ways.
- **Alignment:** never stated, so almost certainly same-date pairs. Vietnam's day t closes before the US day t opens, so the channel that matters (US t−1 to Vietnam t) is not modelled.
- **Method:** Clayton (lower tail), Gumbel (upper tail) and Normal copulas on GARCH-filtered returns, before and after the crisis. The crisis window (Aug 2008 – Apr 2009) is excluded, chosen with the reasoning that all markets "presumably" moved together.
- **Findings (Table 2):**
  - US–Vietnam Clayton θ rises from 0.0945 before to 0.2968 after; Normal ρ rises from 0.061 to 0.238.
  - After the crisis, the Clayton and Normal log-likelihoods are nearly tied (19.52 vs 19.34).
  - The implied lower-tail dependence 2^(−1/θ) is about 0.0007 before and about 0.097 after (our arithmetic; the paper reports none).
  - Conclusion: the two markets are "more prone to crashing than booming together".
- **Weaknesses:**
  - Same-date pairing.
  - No formal test of change and no tail-dependence coefficients reported.
  - The "before" period contains Vietnam's 2007–08 crash.
  - Price limits are ignored: HOSE's ±5% band censors the tails the copulas measure.
  - A thin early market (22 firms in 2003).
- **For us:** weak, contemporaneous, in-sample evidence. It does not contradict our null on swing reversals. Its useful idea is synthesis item 6: US effects may sit only in the left tail, which average-effect models dilute.

## Nguyen & Paientko (2024): forecasting the VN30 index (methods)

Nguyen, H.L. & Paientko, T. (2024). Forecasting the VN30 Index: insights into Vietnam's stock market trends. *Strategies in Accounting and Management* 4(5), 000598 (Crimson Publishers; labelled "Review Article"; published 24 days after submission). **DOI 10.31031/SIAM.2024.04.000598: verified** (it resolves to the publisher's page). File: `methods/`.

- **Data:** VN30 *levels* from Bloomberg: monthly from Feb 2012, plus daily 2018–2023 and 2022–2023. Test sets are 6 months and 5 days. There are no features.
- **Method:** `auto.arima` (Box-Cox, KPSS, AICc). Evaluation only checks whether actuals fall inside the forecast intervals; no error metrics and no baseline.
- **Findings:** the daily models select ARIMA(0,1,0), **a random walk**, giving a flat forecast of 1129.43 against actuals of 1143.16–1160.59 (Tables 2–3). The monthly forecasts are all too low (Jan 2023: 1009.73 vs 1125.07, Table 1). All actuals fall inside the very wide 80% bands. The paper still concludes the VN30 is forecastable.
- **For us:** read correctly, this is weak evidence that daily VN30 levels behave like a random walk, which fits our red-flag rule. Practices to avoid: forecasting levels, checking interval coverage only, five-day holdouts. The VN30 figure of about 80% of HOSE market capitalisation is attributed to "Bloomberg 2023" and needs a primary source.

## Bauer & Swanson (2023): an alternative explanation for the "Fed information effect"

Bauer, M.D. & Swanson, E.T. (2023). An alternative explanation for the "Fed information effect". *American Economic Review* 113(3), 664–700. **DOI 10.1257/aer.20201220: verified** (printed). Replication package doi 10.3886/E181661V1 (openICPSR), which resolves. File: `monetary/`.

- **Surprise series (Sec. I.A).** They use existing series rather than building new ones:
  - the GSS target and path factors (federal funds and Eurodollar futures, 30-minute window around FOMC announcements);
  - the "NS" surprise: the first principal component of five futures rates, scaled so that one unit raises the one-year Treasury yield by 1 pp.
- **Sample:** January 1990 to June 2019; 217 announcements with unscheduled meetings, 206 without. FOMC statements only; speeches and press conferences are excluded.
- **Main finding:** surprises are predictable from public news released before the announcement (Sec. II.B, eq. 7; R² 0.12–0.20, Table 3), because markets underestimate how strongly the Fed responds to data. That explains the "information effect" without any private Fed information. Stocks respond in the standard direction even at "information-heavy" meetings: the S&P 500's 30-minute response to the NS surprise is −8.04 vs −7.14 at other meetings (Table 7).
- **For us:**
  - The cleanest US monetary shock available, but it ends in 2019, so extending it is a data question.
  - Purge surprises using only information released before the announcement, re-estimated on an expanding window for out-of-sample work. Exclude their BBK index, which is published after the announcement (fn. 20).
  - Timing: a 14:00 New York statement arrives at about 01:00–02:00 Vietnam time, before the open.
  - Surprises are estimated regressors (they bootstrap).

## Miranda-Agrippino & Rey (2020): US monetary policy and the global financial cycle

Miranda-Agrippino, S. & Rey, H. (2020). U.S. monetary policy and the global financial cycle. *Review of Economic Studies* 87(6), 2754–2776. **DOI 10.1093/restud/rdaa019: verified** (Crossref; the text is the revised manuscript of 13 April 2020). File: `monetary/`.

- **Data:** one global factor from 858 monthly risky-asset series, 1990–2012, explaining over 20% of their common variation. The US shock is identified by an external instrument: FF4 futures surprises in a 30-minute window, summed by month (first-stage F = 17.930 in the domestic VAR, Table 1). Bayesian VAR, 12 lags, monthly.
- **Findings (Sec. 3.2):** a US tightening causes:
  - the global factor to fall about 40% on impact (about 8% in local stock markets);
  - risk aversion to rise over 50% above trend;
  - global credit and cross-border flows to fall by several percent;
  - global banks' leverage to fall.
  - Countries with floating exchange rates respond similarly.
- **Mechanism:** the dollar is global banks' funding currency; banks constrained by value-at-risk interact with risk-averse asset managers.
- **For us:**
  - The best-founded channel to test: US surprise → risk appetite or dollar → foreign flows → VN30 and banks.
  - Caveats: their evidence is monthly and builds over months; daily data would show only the short run. Vietnam is not in their samples. It is a frontier market with a managed exchange rate, foreign-ownership limits and price limits, any of which can delay or truncate the response.

## Baker, Bloom & Davis (2016): measuring economic policy uncertainty

Baker, S.R., Bloom, N. & Davis, S.J. (2016). Measuring economic policy uncertainty. *Quarterly Journal of Economics* 131(4), 1593–1636. **DOI 10.1093/qje/qjw024: verified** (Crossref; the text is the accepted manuscript). File: `geopolitical/`.

- **Construction:**
  - Monthly US index: share of articles in 10 newspapers containing terms for economy, policy and uncertainty, normalised to mean 100 over 1985–2009.
  - Daily index: Newsbank, about 1,500 US papers. The paper warns that changes in the archive's coverage over time can distort the series.
  - Audit: about 12,000 articles were coded by hand; the human and computer indices correlate 0.86 (quarterly).
- **Findings:** firm implied volatility rises with EPU (coefficient on log EPU 0.432, Table II); investment and employment fall for firms exposed to government demand; in a VAR, industrial production falls about 1.1%.
- **Point-in-time issues:** "We update the daily EPU index at approximately 9am EST each day." A value for day d posted at 9am New York time on d+1 can only enter the Vietnamese session of d+2. Revisions are not documented, and the values depend on the query date and the normalisation base.
- **For us:** daily EPU is at best a complement to GPR, with a low prior given our nulls. If used: archive dated copies from now on, treat the back history as latest-vintage robustness only, work in logs, and build shocks as for GPR.

## Forbes & Rigobon (2002): no contagion, only interdependence

Forbes, K.J. & Rigobon, R. (2002). No contagion, only interdependence: measuring stock market comovements. *Journal of Finance* 57(5), 2223–2261. **DOI 10.1111/0022-1082.00494: verified** (Crossref). File: `international-spillover/`.

- **The bias:** with y = a + b·x + e and no omitted variables or endogeneity, the slope b is the same in calm and turbulent periods, but the correlation rises with the variance of x:
  - ρ* = ρ·√[(1+δ)/(1+δρ²)], where δ is the relative rise in variance (eqs. 9–10).
  - Adjusted correlation: ρ = ρ*/√(1+δ[1−ρ*²]) (eq. 11).
  - Valid only without global common shocks or feedback.
- **Time zones:** they use rolling two-day average returns, a VAR with 5 lags and interest-rate controls.
- **Findings:** cases of contagion before vs after adjustment:

  | Crisis | Unadjusted | Adjusted |
  |---|---|---|
  | 1997 Asia | 15 | 1 |
  | 1994 Mexico | 6 | 0 |
  | 1987 US | 4 | 0 |

- **For us:**
  - Test regime change with regression betas and interactions, not correlations.
  - Fix regimes from US events in advance.
  - Pair US t−1 with Vietnam t instead of averaging over two days, since the time-zone ordering is clean.
  - Price limits truncate crash-day returns: use cumulative returns over several days, or flag days that hit a limit.
  - The "stronger after 2008" claims of Thuan (2011) and Nguyen et al. (2017) are exposed to exactly this bias.

## Hamao, Masulis & Ng (1990): correlations in price changes and volatility across international stock markets

Hamao, Y., Masulis, R.W. & Ng, V. (1990). Correlations in price changes and volatility across international stock markets. *Review of Financial Studies* 3(2), 281–307. **DOI 10.1093/rfs/3.2.281: verified** (Crossref; the file is a scan, read by OCR, and Table 1 is unreadable). File: `international-spillover/`.

- **Data:** Tokyo, London and New York, daily opening and closing prices, April 1985 to March 1988. Each return is split into close-to-open and open-to-close parts.
- **Method:** MA(1)-GARCH(1,1)-M. The squared residual of the open-to-close return of the market that traded most recently enters the domestic variance; that market's return enters the domestic mean.
- **Findings:**
  - Volatility spills into Tokyo's open-to-close return from New York: f = .0464 (t = 5.24, Table 3). This is the only spillover that survives in the pre-crash sample.
  - Foreign returns move the domestic open strongly: New York to Tokyo, t = 7.69 (Table 7).
  - They attribute mean spillovers into open-to-close returns to stale opening prices.
- **For us:** the template for the gap vs intraday test (see the design table above). Two warnings:
  - Do it on opens that actually traded in the HOSE opening auction.
  - The open is known only after 09:00, so it can be an outcome in Paper 3 but never a Paper 1 feature.

## Paper 1 novelty check, first pass (2026-11-25; web search, every hit verified on Crossref, PDFs not yet read)

**Verdict:** the *question* (when does a trend end?) and several of the *tools* have precedents. The *combination* Paper 1 uses has none in this search:
- stock-level directional-change swings with a volatility-scaled threshold;
- a proper survival treatment (censoring, landmark discrete-time hazard);
- an emerging market with daily price limits;
- point-in-time global and bank information;
- purged walk-forward tests against a mechanical baseline.

The paper must cite and position against the work below, not claim to be first to model reversal timing.

| Prior work | What it does | How Paper 1 differs |
|---|---|---|
| Lunde & Timmermann (2004), "Duration dependence in stock prices: an analysis of bull and bear markets", *J. Business & Economic Statistics* 22(3), 253–273, doi 10.1198/073500104000000136 | Hazard of bull or bear market *termination* for the US index. Bull hazards fall with age, bear hazards rise. Higher interest rates raise bull hazards. | Index-level phases defined by large fixed filters vs stock-level swings with a volatility-scaled threshold. In-sample duration dependence vs out-of-sample prediction. **Our D-019 result (age adds nothing once distance is known) speaks directly to their duration dependence:** a contribution, not a threat. |
| Zakamulin (2023), "Revisiting the duration dependence in the US stock market cycles", *Applied Economics* 55(4), 357–368, doi 10.1080/00036846.2022.2089344 | Two centuries of US data: positive duration dependence in bear markets and in most bull markets. | As above. |
| Adegboye & Kampouridis (2021), "Machine learning classification and regression models for predicting directional changes trend reversal in FX markets", *Expert Systems with Applications* 173, 114645, doi 10.1016/j.eswa.2021.114645 | **Closest in method:** machine learning predicts when a DC trend reverses (overshoot length) in FX. | FX vs equities. Regression or classification without censoring vs survival models. No point-in-time global information, mechanical baseline or trading-cost test. To be read in full. |
| Hu & Zhou (2024), "Trading signal survival analysis: a framework for enhancing technical analysis strategies in stock markets", *Computational Economics* 64(6), 3473–3507, doi 10.1007/s10614-024-10567-8 | **Closest in tool:** survival models of the time until a stock reaches an investment target after a technical signal, about 380 stocks, used to filter signals. | Time-to-target after a signal vs time-to-reversal of a swing. US/developed stocks. To be read in full: the most important threat to check. |
| Gao, Jiang, Xiong & Xiong (2023), "Daily momentum and new investors in emerging stock markets", SSRN doi 10.2139/ssrn.4527729 (NBER w31839) | About half of emerging markets show daily momentum, while developed markets show daily reversal. China's price limits can mechanically extend moves. | Context for price limits and reversal timing in Vietnam. Worth citing in the price-limit discussion. |

**Also found, lower relevance:**
- survival analysis of index declines during COVID (Bieszk-Stolorz & Dmytrów, *Risks* 2021);
- time to reach target prices in India (Chatterjee & Kumar);
- a 2015 IEEE conference paper using a Cox model for buy and sell points (doi 10.1109/besc.2015.7365968, not checked).

**PDFs to get, in priority order:**
1. Hu & Zhou (2024);
2. Adegboye & Kampouridis (2021), open copy in the Essex repository;
3. Lunde & Timmermann (2004), working-paper version on the author's UCSD page;
4. Zakamulin (2023);
5. Gao et al. (2023), open on NBER or the author's page.

## Block E related work: bank asset quality and investor attention (2026-11-25)

Six papers, each read in full, with key numbers checked against the text. Files are in `bank-asset-quality/` and `investor-attention/`.

**Synthesis for Paper 1 (block E):**
- **Asset quality is reflected in prices by the time statements appear.** The three annual studies find NPL, provisions or reserves line up with returns or valuations *over the same period the statements describe* (Eng & Nabar 2007; Agusman et al. 2009; Tran & Ha 2024). None shows they predict later returns.
- **Reactions are fast.** The one daily event study (Huang et al. 2012, China) finds the reaction concentrated in days −1 to +4 and gone by +10.
- **Attention effects in Vietnam are small and short-lived.** A search-sentiment effect of about 2 days reverses at t+2. Once publication lag is respected it shrinks to about 5 bp per SD (Nguyen & Pham 2018). Returns appear to drive search attention more than the reverse (Pham et al. 2024).
- Together this explains the D-023 development result: block E beats the mechanical baseline but adds nothing beyond local market features, because by our conservative entry time (5th session after the later of the deadline and the PDF date) the information is already in returns, volatility and volume.
- None of the six uses first-released data or real-time timestamps. Our design is stricter than all of them.

**Ideas raised by these readings that are NOT adopted** (they would change block E after its development results; at most robustness checks fixed before the final run, each logged in DECISIONS.md first):
- an NPL "surprise" against an expectation fitted only on past data (Eng & Nabar's approach);
- flags for Vietnamese regulatory regimes that affect reported NPLs: the VAMC transfers from 2013, Resolution 42/2017, and Circular 01/2020 (COVID restructuring), as caveats;
- a diagnostic event study around actual PDF dates, to measure how much of any reaction comes before our entry lag.

| Paper | Data and timing | Key numbers | Use |
|---|---|---|---|
| Eng & Nabar (2007), *J. Int'l Financial Management & Accounting* 18(1), 18–38, doi 10.1111/j.1467-646x.2007.01006.x | 35 banks in Hong Kong, Malaysia and Singapore, annual, 1993–2000. "Unexpected" components come from expectation models fitted on the full sample (look-ahead). | Unexpected provisions +5.79 (t = 3.99); unexpected ΔNPL −0.45 (t = −1.57, n.s.) (Table 6). Provisions lose their signalling value in the 1997–98 crisis. | NPL *changes* carry the least information among loan-loss items |
| Agusman, Monroe, Gasbarro & Zumwalt (2009), SSRN working paper 1227362, doi 10.2139/ssrn.1227362 | 42 banks in 9 Asian countries, annual, 1999–2007. The reserve ratio covers the same year as the return. | Reserves / gross loans: −0.321*** (fixed effects, Table 2) | Contemporaneous association only |
| Tran & Ha (2024, printed 2025), *Macroeconomics and Finance in Emerging Market Economies* 18(2), 278–300, doi 10.1080/17520843.2024.2419758 | 20 Vietnamese banks, annual, 2010–2023. NPL = groups 3–5 / total loans, as ours. | NPL −1.547*** on Tobin's Q (Table 4); mean NPL 1.8% | The only Vietnamese evidence: NPL is reflected in valuation levels. The tables have typos and the estimator is unclear. |
| Huang, Schwienbacher & Zhao (2012), *J. Int'l Financial Markets, Institutions & Money* 22, 233–252, doi 10.1016/j.intfin.2011.09.004 | China, 424 loan announcements, daily event study | CAR [0, +1] −0.277% (p = .005), [−1, +4] −0.461%, [−1, +10] not significant (Table 3). The lending bank's NPL is not significant (Table 5). | Timing lesson: disclosure reactions finish within about a week |
| Pham, Pavelkova, Popesko, Hoang & Huynh (2024), *Financial Innovation* 10:123, doi 10.1186/s40854-023-00576-1 | Weekly Google Trends (fintech terms) vs an index of 8 banks, 2017–2021, VAR–Granger | BankReturn → FinLending χ² 18.42***, reverse 23.70*** (Table 7). The factor model is weak (KMO 0.501). | Search attention vs our news supply. Full-sample factor scaling is exactly the look-ahead we avoid. Ambiguous Granger table layout. |
| Nguyen & Pham (2018), *Journal of Asian Finance, Economics and Business* 5(4), 45–56, doi 10.13106/jafeb.2018.vol5.no4.45 (our copy is the SSRN working paper) | Daily Vietnamese Google search sentiment, 2011–2018 | One SD of sentiment ≈ −7.7 bp over 2 days, then +6.3 bp at t+2 (Table 2); about 5 bp with real-time timing (Table 3E) | Attention effects are tiny and reverse quickly. Weak venue. Check the published numbers before citing. |

**To read next for this area:** Nguyen, Schinckus & Nguyen (2019), "Google search and stock returns in emerging markets", *Borsa Istanbul Review* 19(4), 288–296, doi 10.1016/j.bir.2019.07.001 (verified on Crossref; it covers Vietnam).

## Paper 1 novelty check, second pass: papers read in full (2026-11-25)

Files are in `trend-duration/`. Every number below was checked against the extracted text.

**The closest precedent, found through Hu & Zhou's references:** Yao, Partington & Stevenson (2005), "Run length and the predictability of stock price reversals", *Accounting & Finance* 45(4), 653–671, doi 10.1111/j.1467-629x.2005.00156.x (verified; abstract only so far, **PDF still needed**).
- **What it does:** survival analysis of *price runs* (consecutive same-sign daily changes) in the Australian All Ordinaries index. Lagged price changes and the number of recent runs shift the probability of a reversal.
- **Out of sample, the models predict run lengths worse than a random walk**, which the authors read as market efficiency.

**Final verdict and positioning.** Paper 1 is not the first to apply survival analysis to price reversals, nor the first to apply machine learning to directional-change reversals. Its defensible contribution:
1. **The unit of analysis.** Volatility-scaled directional-change swings of individual stocks, not noisy daily runs (Yao et al.), fixed-percentage FX DC events (Adegboye & Kampouridis) or index bull and bear phases (Lunde & Timmermann; Zakamulin). Scaling by ATR also answers Hu & Zhou's objection that survival data from different stocks cannot be pooled.
2. **A positive out-of-sample result where the closest precedent failed.** Yao et al. find no out-of-sample predictability for daily runs; our development data show modest but robust predictability (C ≈ 0.60), from a far stricter design: purged walk-forward, a mechanical baseline, shuffled-label controls. Whether it holds is decided by the final run.
3. **Age vs distance.** The duration-dependence papers model the hazard as a function of age only. Under a filter-type label, age is mechanically tied to the distance from the trigger. Paper 1 conditions on distance and finds that age adds nothing (D-019). This refines their result for our setting and does not overturn it for index cycles.
4. **The setting.** An emerging market with daily price limits, information timed to what was public at decision time, global and bank-fundamental information, and realistic trading frictions.

**Presentation lesson (no new test):**
- Report the age-only hazard first (life table or Kaplan–Meier by swing direction, like the bull/bear asymmetry), then show the age effect disappearing once distance is in the model. This uses the existing D-015 and D-019 results.
- Frame the null for US rates as out-of-sample and about overnight global changes, so it is not set against Lunde & Timmermann's in-sample result for domestic rates.

| Paper | Design | Key results (checked) | Positioning |
|---|---|---|---|
| Lunde & Timmermann (2004), *J. Business & Economic Statistics* 22(3), 253–273, doi 10.1198/073500104000000136 (our file is the 2002 working paper; check numbers against print) | US index, daily, 1885–1997. Bull and bear phases from first-passage filters (20/15 … 15/10%). Discrete-time logit hazard with a flexible baseline. Interest-rate covariates. In-sample. | With rates controlled (15/10 nominal): the bull baseline hazard "drops sharply from five to two percent per week" after six months; the bear hazard rises "from five to about eight percent per week". Rate rises raise bull hazards slightly and cut bear hazards a lot. | The closest precursor in method. Their age-only hazard averages over the distance to the trigger. |
| Zakamulin (2023), *Applied Economics* 55(4), 357–368, doi 10.1080/00036846.2022.2089344 | US index, monthly, 1802–2019. Pagan–Sossounov dating, 63 bull and 62 bear markets. Piecewise-linear empirical hazard and parametric fits. | Bear duration dependence "strictly positive"; positive for 93% of bull markets. Its two-sided dating window means turning points are known only after the fact, and its minimum durations push young-age hazards toward zero. | Background on mixed duration-dependence evidence |
| Adegboye & Kampouridis (2021), *Expert Systems with Applications* 173, 114645, doi 10.1016/j.eswa.2021.114645 (our file is the preprint) | 20 FX pairs, 10-minute data, monthly datasets with 70/30 splits. Fixed-percentage DC thresholds. Classifies whether an overshoot follows a DC, then predicts overshoot length from DC length alone by genetic programming. | Classification accuracy 0.817 (Table 4); overshoot RMSE 18.617 vs 20.265 for GP only, a gain that is not significant (Hommel p = 0.327, Table 6). | **Closest machine-learning precedent.** It predicts from completed spells only, with no censoring and no update as a trend ages; a landmark hazard handles both. Its model uses only DC length, i.e. our mechanical baseline. |
| Hu & Zhou (2024), *Computational Economics* 64(6), 3473–3507, doi 10.1007/s10614-024-10567-8 (read by me) | About 380 S&P 500 stocks, 2018–2022, test year 2022 only. The event is reaching +5% (or −5%) within 22 days after a MACD or RSI signal. Deep survival models filter the signals. | The filtered strategies improve on the original signals in both a bear and a bull half of 2022. | Survival models in stock trading. The event is a target return after a signal, not a swing reversal. Cites Yao et al. (2005). |
| Gao, Jiang, Xiong & Xiong (2023), NBER WP 31839 (not peer-reviewed) | China 2005–2019 with account-level data; 42 markets from Datastream. "Daily momentum" means the day-d return predicts day d+1. | China long-short 0.37% per day (t = 9.47), cut by about 40–60% when limit-hit days are removed (Table II). **Vietnam (Table VIII): value-weighted +0.32% (t = 4.93), equal-weighted −0.43% (t = −5.84).** | Price limits mechanically push continuation into the next session or two; large caps continue, small caps reverse. This motivates direction-signed limit-hit features and the 5-session horizon. |
