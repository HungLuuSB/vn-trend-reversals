# When Do Trends Reverse? A Survival Analysis of Price Swings in the Vietnamese Stock Market Under Global Shocks

Research proposal · Nov 24, 2026 · @Hung · Nhat Hao Pham Ngo (co-author, added Nov 26, 2026)

## Abstract

This study asks whether global shocks that reach Vietnam overnight, from US markets, China, gold and geopolitics, change when trends end in Vietnamese stocks. Recent machine-learning work on predicting peaks and troughs reports near-perfect accuracy that most likely comes from look-ahead leakage and from defining every one-day reversal as a turning point.

We define price swings causally, using directional-change events with volatility-scaled thresholds. We then model the time until the current swing reverses as a right-censored survival problem, because on the day of prediction the swing has not yet ended.

The sample covers VN30 constituents (point-in-time membership) and all listed banks from 2012 to 2026. It is combined with overnight US indices, the VIX, the dollar index, US yields, gold, oil, Asian indices and a geopolitical risk index. Models range from Kaplan–Meier and Cox regression to survival forests, gradient boosting and a neural hazard model.

Evaluation is walk-forward, using the time-dependent C-index, integrated Brier score, calibration and a cost-adjusted trading test. The data come from a point-in-time data platform with lineage, which enforces the leakage controls by construction.

## Tóm tắt (Vietnamese summary)

Nghiên cứu này đặt câu hỏi: các cú sốc toàn cầu truyền qua đêm từ thị trường Mỹ, Trung Quốc, giá vàng và rủi ro địa chính trị có làm thay đổi thời điểm kết thúc xu hướng của cổ phiếu Việt Nam hay không. Các nghiên cứu học máy gần đây về dự báo đỉnh và đáy báo cáo độ chính xác gần như tuyệt đối. Kết quả này nhiều khả năng do rò rỉ dữ liệu tương lai và do coi mọi lần đảo chiều một ngày là một đỉnh hoặc đáy.

Chúng tôi định nghĩa các con sóng giá theo phương pháp thay đổi hướng (directional change), với ngưỡng điều chỉnh theo mức biến động và chỉ xác nhận khi đã xảy ra. Thời gian còn lại của con sóng hiện tại được mô hình hóa bằng phân tích sống sót (survival analysis) với dữ liệu bị kiểm duyệt phải, vì tại thời điểm dự báo con sóng chưa kết thúc.

Mẫu nghiên cứu gồm các cổ phiếu VN30 (theo danh mục tại từng thời điểm) và toàn bộ ngân hàng niêm yết, giai đoạn 2012–2026. Dữ liệu toàn cầu gồm chỉ số Mỹ, VIX, chỉ số đô la (DXY), lợi suất trái phiếu Mỹ, vàng, dầu, chỉ số châu Á và chỉ số rủi ro địa chính trị.

Mô hình được đánh giá theo phương pháp walk-forward bằng C-index, Brier score tích hợp, độ hiệu chuẩn và một chiến lược giao dịch có tính phí. Dữ liệu được lấy từ nền tảng VN Bank Data Platform, bảo đảm tính đúng thời điểm (point-in-time) và truy vết được nguồn gốc của từng con số.

## Background and motivation

Knowing when a trend is likely to end matters more to traders and risk managers than tomorrow's price. Yet the research that targets turning points directly is thin, and its strongest-looking results do not survive scrutiny.

**Why Vietnam, and why now.** The Vietnamese market is dominated by retail investors, has daily price limits and depends heavily on foreign flows. Vietnam moved to FTSE Russell's Secondary Emerging Market status on 21 September 2026, with index inclusion phased until September 2027 ([World Bank](https://www.worldbank.org/en/news/feature/2026/04/22/a-turning-point-for-viet-nam-s-capital-markets)). Closer integration should make global shocks matter more, and that can be measured.

**Turning-point prediction with machine learning.** [Abolmakarem et al. (2024)](https://doi.org/10.1016/j.iswa.2024.200449) predict ten engineered targets, including next-day peaks, troughs and the distance between them, for four FTSE 100 stocks. They report about 97% accuracy for next-day direction and R² ≈ 0.9999 for next-day returns. Four features of the design likely explain these figures:

- The input ln(Closeᵢ / Closeᵢ₋₁) is almost the same quantity as the return target. A one-day misalignment lets the network copy it.
- The data split for the neural network appears to be random, so test days sit next to training days that share overlapping indicators.
- Peak height and trough depth are measured against the whole sample's minimum and maximum, which uses future data.
- A "peak" is any up day followed by a down day. Under a coin-flip model about 25% of days qualify, so the reported 75% accuracy matches always predicting "no peak".

**Directional-change research.** [Adegboye and Kampouridis (2021)](https://doi.org/10.1016/j.eswa.2021.114645) define trends with directional-change thresholds and use classification and regression to predict when they reverse in foreign-exchange markets. That work treats completed trends as the training target. It does not handle the open, censored trend that exists on every prediction day, and it does not study equities or global spillovers.

**Spillovers into Vietnam.** Studies of how US and regional shocks reach Vietnam usually model index returns or volatility with VAR, GARCH or connectedness methods, not the timing of trend reversals. A systematic literature search in the first month will confirm this gap.

**The gap.** No study we know of models trend-reversal timing as a censored time-to-event problem, with causal swing labels, leakage-free evaluation and global covariates, in an emerging equity market.

## Research questions and hypotheses

The study tests five hypotheses. Each one is useful whichever way it comes out: a null result on a well-built test is evidence about market efficiency.

| # | Research question | Hypothesis | Test |
| --- | --- | --- | --- |
| RQ1 | Is the hazard of a swing reversing predictable out of sample? | H1: feature-based models beat a no-feature Kaplan–Meier baseline. | C-index and integrated Brier score, walk-forward |
| RQ2 | Do overnight global signals add information beyond local features? | H2: adding the global block improves out-of-sample fit; US equity falls and VIX jumps raise the hazard that an up-swing ends. Banks react more to rates and the dollar than other VN30 stocks. | Block ablation; coefficient signs; bank × global interactions |
| RQ3 | Do trends "age"? | H3: the baseline hazard is not flat; the chance of reversal changes with swing age. | Shape of the estimated baseline hazard against a constant-hazard model |
| RQ4 | Has sensitivity to global shocks risen with market upgrading? | H4: global effects are larger after the FTSE upgrade announcement of 7 October 2025. | Interaction with a post-announcement indicator; placebo dates |
| RQ5 | Is the predictability worth anything after costs? | H5: an exit rule based on the predicted hazard beats buy-and-hold and a fixed directional-change rule on risk-adjusted return. | Sharpe ratio, maximum drawdown, deflated Sharpe ratio |

RQ4 is exploratory. The upgrade took effect only on 21 September 2026, so the post-upgrade sample is short; the announcement date gives about 13 months of post-event data.

## Data and sample

The sample is every VN30 constituent at each date, plus all listed banks, with daily data from 2012 to the latest available date in 2026.

**Stock universe.**

- **VN30, point-in-time.** A stock enters the sample on the date it joins the VN30 and leaves on the date it exits, using the semi-annual index reviews. Stocks that later left or were delisted stay in the sample for the years they were members, which avoids survivorship bias.
- **All listed banks** (about 27, across HOSE, HNX and UPCoM), included for their whole listed history. This adds bank fundamentals and news, and allows the bank versus non-bank comparison in RQ2.
- Exclusions: stocks with fewer than 250 trading days, and days with trading halts.

**Local data (Vietnam).**

- Daily open, high, low, close and volume, both raw and adjusted for dividends and splits.
- The exchange reference price and the ceiling and floor prices. Daily limits are ±7% on HOSE, ±10% on HNX and ±15% on UPCoM ([Stockbiz](https://stockbiz.vn/en/learn/glossary/price-limits)).
- VN-Index level and breadth, and daily foreign net buying, if the history is available.
- For banks: quarterly financial ratios (for example the non-performing loan ratio and capital adequacy ratio) using the first-released figures and their actual publication dates, plus daily counts of news mentions.

**Global data (observed overnight).**

| Series | Source | Identifier | Closes (Vietnam time) |
| --- | --- | --- | --- |
| S&P 500, Nasdaq Composite | yfinance | `^GSPC`, `^IXIC` | 03:00 (US summer) or 04:00 (US winter), next day |
| VIX | FRED | `VIXCLS` | Same as US stocks |
| US 10-year Treasury yield | FRED | `DGS10` | Same as US stocks |
| Dollar index (DXY) | yfinance | `DX-Y.NYB` | Same as US stocks |
| Gold, front-month futures (roll-adjusted) | yfinance | `GC=F` | Settles 00:30 or 01:30, next day |
| Brent crude oil | FRED | `DCOILBRENTEU` | Daily spot price |
| Hang Seng, CSI 300 | yfinance | `^HSI`, `000300.SS` | 15:00 and 14:00 |
| USD/VND, USD/CNY | yfinance, FRED | `VND=X`, `DEXCHUS` | Daily |
| Geopolitical risk index (daily) | [Caldara and Iacoviello](https://www.matteoiacoviello.com/gpr.htm) | Downloaded file, versioned | Published with a lag; used only once released |

Two gaps in FRED decide the source mix. FRED keeps only [10 years of daily S&P 500 history](https://news.research.stlouisfed.org/2014/04/sp-series-update-2/) and [removed LBMA gold prices in January 2022](https://news.research.stlouisfed.org/2022/01/ice-benchmark-administration-ltd-iba-data-to-be-removed-from-fred/). yfinance fills those gaps but is unofficial, so every raw download is archived before use (see Data infrastructure).

## Methodology

The method has four steps: label swings without looking ahead, turn each open swing into survival data, describe each day with feature blocks, and fit models of increasing flexibility.

### 1. Swing definition

A swing reverses only when the price retraces a volatility-scaled threshold from its running extreme. For an up-swing with running maximum close M since the last confirmed trough, a reversal is confirmed on the first day t where:

```latex
P_t \le M_t \,(1 - \theta_{i,t}), \qquad \theta_{i,t} = k \cdot \frac{\mathrm{ATR}_{20}(i,t-1)}{P_{t-1}}
```

Down-swings mirror this with the running minimum. The threshold uses only the trailing 20-day average true range, so the label never uses future volatility. The main specification fixes k = 2 in advance; k = 1.5 and k = 3 are robustness checks. Adjusted closes are used, and days that close at the price limit are flagged.

### 2. Survival setup

Each row is one stock on one trading day inside a swing that has not yet been confirmed as reversed. The time scale is the swing's age in trading days. The event is the next confirmed reversal. A swing is right-censored when the sample ends, the stock leaves the universe or trading is halted.

The main quantity is the discrete-time hazard, the probability that the swing reverses at age a given that it has lasted until then:

```latex
h_i(a \mid x_{i,t}) = \Pr(T_i = a \mid T_i \ge a,\; x_{i,t}), \qquad S_i(a) = \prod_{s \le a} \big(1 - h_i(s \mid x_{i,t})\big)
```

From the survival curve S we report the probability of reversal within 5, 10 and 20 trading days and the median remaining life of the swing. Features are updated each day, so every day is a new prediction for the same open swing.

### 3. Feature blocks

| Block | Contents | Used for |
| --- | --- | --- |
| A. Swing state | Direction, age, move so far relative to the threshold, distance from the running extreme | All models |
| B. Stock technicals | Lagged returns, ATR, RSI, volume relative to its 20-day average, recent limit hits | All models |
| C. Local market | VN-Index swing state and breadth, foreign net flows | All models |
| D. Global overnight | US index returns, VIX change, DXY, US 10-year change, gold, oil, Hang Seng, CSI 300, USD/VND, USD/CNY, geopolitical risk | RQ2 and RQ4 |
| E. Bank fundamentals | First-released quarterly ratios, news mention counts | Bank subsample |

### 4. Models

1. **Kaplan–Meier**, with no features: the baseline every model must beat.
2. **Cox proportional hazards** with time-varying covariates: interpretable effects for the hypothesis tests.
3. **Discrete-time logistic hazard** with elastic-net penalty: the main interpretable model.
4. **Random survival forest** and **gradient-boosted discrete-time hazard**: nonlinear effects and interactions.
5. **Neural hazard model**: a GRU sequence encoder over the last 60 days with a logistic-hazard output layer.

Effects are explained with SHAP values for the tree and neural models and with coefficients for the linear models. RQ2 compares each model with and without block D.

## Leakage controls and time alignment

Every prediction is made at one fixed moment: the HOSE open at 09:00 Vietnam time on day t+1. A value may enter a feature only if it was publicly available before that moment. The rules below enforce this, and each one is checked automatically in the data pipeline.

1. **Availability timestamps.** Every observation stores `available_at_utc`, the close or release time of its market. A pipeline test fails if any feature row has `available_at_utc` later than the decision time.
2. **Market calendar.** US markets for day t close at 03:00 or 04:00 Vietnam time on day t+1, so they are usable for the session on day t+1. Hang Seng (15:00) and CSI 300 (14:00) for day t are also usable on day t+1. US daylight saving time is handled with a time-zone database, not a fixed offset.
3. **Vietnamese holidays.** When HOSE is closed and other markets trade, as during Tết, global features use the cumulative return since the last Vietnamese session.
4. **Causal labels.** Swing confirmation and its threshold use only past prices. The future enters only through the target (time to the next reversal), never through a feature.
5. **Point-in-time reference data.** VN30 membership is taken as of each date. Bank financials enter on their actual publication date, using the first-released figures rather than later restatements.
6. **Chronological splits only.** Scaling and tuning are fitted inside each training window. Training rows whose swing ends inside the test window are purged, with a 20-day embargo.
7. **Sanity checks.** A model trained on shuffled labels must score a C-index near 0.5. Any test-period result far above published benchmarks triggers a leakage review before it is reported.

As an appendix, the study will rebuild the Abolmakarem et al. (2024) targets on the same Vietnamese data. It will compare a random split with a chronological split and correctly aligned inputs, to show how much reported accuracy depends on leakage.

## Evaluation design

Models are judged out of sample, year by year, on statistical accuracy first and on trading value second.

**Walk-forward scheme.** Training starts in 2012 with an expanding window. Models are refitted each January and tested on the following calendar year, giving test years 2017 to 2026. Hyperparameters are tuned with purged, embargoed cross-validation inside each training window only.

**Statistical metrics.**

| Metric | What it measures |
| --- | --- |
| Time-dependent C-index (Uno) | Whether swings that reverse sooner get higher predicted risk |
| Integrated Brier score (IPCW) | Accuracy of the whole survival curve, corrected for censoring |
| Calibration at 5, 10 and 20 days | Whether a predicted 30% chance of reversal happens about 30% of the time |
| Time-dependent AUC | Ranking quality at each horizon |

Models are compared with a paired block bootstrap over test days, and with Diebold–Mariano tests on Brier loss.

**Economic test.** The strategy is long-only, because short selling individual stocks is not generally available in Vietnam. It holds a stock during an up-swing and exits when the predicted probability of reversal within 5 days exceeds a threshold τ, chosen in the training window. Benchmarks are buy-and-hold and a fixed directional-change exit rule.

The simulation respects local trading rules:

- Shares bought cannot be sold before settlement (T+2).
- A sell order on a limit-down day is assumed not to fill.
- Round-trip cost is assumed at 0.4% (brokerage fees plus the 0.1% tax on sales), with 0.2% and 0.8% as sensitivity cases.

Results are reported as annualised return, Sharpe ratio, maximum drawdown, turnover and the deflated Sharpe ratio, which corrects for the number of configurations tried.

**Robustness checks.**

- Thresholds k = 1.5 and k = 3.
- Sub-periods: 2012–2019, 2020–2021 (COVID), 2022 (corporate-bond and real-estate stress) and 2023–2026.
- Banks versus other VN30 stocks.
- Excluding days at the price limit.
- Decision time moved to the HOSE close (14:45).
- For RQ4, placebo break dates in place of the FTSE announcement.

## Data infrastructure

The data come from the VN Bank Data Platform, an existing project that turns Vietnamese market data, bank filings and news into tested, traceable tables. The research uses its batch layer and adds the global series and the swing tables.

&#91;embedded content: data flow · sources to frozen snapshot\]

Every source lands unchanged in a raw archive, is modelled into tested tables, and is then frozen. The analysis never reads live tables.

**What the platform already provides:** point-in-time joins (a value is used only after its publication date), versioned bank financials with publication dates, exchange-calendar and price-limit checks, and lineage from each number to its source file and pipeline run.

**What this study adds:**

- A daily global-markets ingestion job (yfinance, FRED and the geopolitical risk file) that stores an availability timestamp for each value.
- Price ingestion widened from banks to all VN30 stocks, with point-in-time index membership.
- The price-limit check compared against the exchange reference price, so ex-dividend days do not raise false alarms.
- Swing and risk-set tables, plus a test that no feature is timestamped after the 09:00 decision time.
- A frozen snapshot of the final dataset in Parquet, identified by its content hash. The hash is cited in the paper so results can be reproduced exactly.

**Computing resources.** The dataset is about 220,000 stock-days, a few hundred megabytes. All models except the neural one run on a CPU with 16 GB of RAM; the small GRU model fits in 4 GB of GPU memory. An always-on Arch Linux laptop (RTX 2050, 16 GB RAM) runs ingestion and the databases. A desktop (Core i5-14400F, GTX 1660 Super, 16 GB RAM) runs the heavier walk-forward experiments over SSH.

## Expected contributions and target journals

The study offers four contributions:

1. **A new formulation.** Trend-reversal timing is treated as a censored time-to-event problem with causal swing labels, replacing noisy one-day peak and trough targets.
2. **Evidence on global transmission.** It measures whether overnight US, Chinese, gold and geopolitical shocks change the timing of reversals in an emerging market, and whether that changed around market upgrading.
3. **A leakage-audited benchmark.** It shows how much reported accuracy in this literature depends on data leakage, using a reproducible pipeline.
4. **Economic relevance under real trading rules:** price limits, T+2 settlement and long-only constraints.

| Journal | Why it fits |
| --- | --- |
| Expert Systems with Applications | Publishes directional-change and machine-learning trading work, including Adegboye and Kampouridis (2021) |
| Pacific-Basin Finance Journal | Asian markets, spillovers, market microstructure |
| Journal of Forecasting | Forecast evaluation and survival-style prediction |
| Emerging Markets Review | Emerging-market integration and the upgrade question |
| Intelligent Systems with Applications | Same journal as the paper critiqued; suitable for the leakage-audit angle |

The final choice depends on the results. A strong RQ2/RQ4 finding points to a finance journal; a strong methods and leakage result points to a machine-learning or forecasting journal.

## Timeline

The study takes about nine months, from December 2026 to a first submission in early August 2027.

&#91;embedded content: proposal timeline · Dec 2026 to Aug 2027\]

The one hard gate is freezing the data snapshot in mid-February 2027 (moved forward to early December 2026 by D-024, research/paper1/DECISIONS.md): all modelling runs on that snapshot, and a data problem found later reopens it. Phases overlap by two weeks so writing of methods can start while experiments finish.

## Risks and limitations

The largest risks are weak predictability and data gaps. Both have a fallback that still yields a publishable paper.

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Reversal timing is barely predictable | RQ1 and RQ5 come out null | Report it as evidence on market efficiency; focus on calibration, the global block and duration dependence |
| Short post-upgrade sample | RQ4 has low statistical power | Use the October 2025 announcement as the break; present RQ4 as exploratory |
| yfinance or vnstock changes or breaks | Data cannot be re-downloaded | Archive every raw response; analysis runs on a frozen snapshot; FRED used where possible |
| Foreign net-flow history unavailable | Block C is incomplete | Drop the series and state it as a limitation |
| Delisted VN30 members lack history | Survivorship bias | Source their full history before freezing the snapshot; report coverage |
| Price limits and thin trading distort swings | Biased labels on illiquid days | Limit-hit flags; robustness check excluding them |
| Overfitting across many configurations | Inflated results | Main specification fixed in advance (k = 2, 5-day horizon); deflated Sharpe ratio |

**Limitations.** The study uses daily data only, so intraday reversals are not captured. Trading costs are assumed rather than observed. Results for Vietnam may not carry over to markets without price limits or with more institutional investors.

## References

Core references for the proposal; the literature search in month 1 will extend them.

- Abolmakarem, S., Abdi, F., Khalili-Damghani, K., & Didehkhani, H. (2024). A multi-stage machine learning approach for stock price prediction: Engineered and derivative indices. *Intelligent Systems with Applications*, 24, 200449. [doi](https://doi.org/10.1016/j.iswa.2024.200449)
- Adegboye, A., & Kampouridis, M. (2021). Machine learning classification and regression models for predicting directional changes trend reversal in FX markets. *Expert Systems with Applications*, 173, 114645. [doi](https://doi.org/10.1016/j.eswa.2021.114645)
- Bailey, D. H., & López de Prado, M. (2014). The deflated Sharpe ratio: Correcting for selection bias, backtest overfitting and non-normality. *Journal of Portfolio Management*, 40(5), 94–107.
- Caldara, D., & Iacoviello, M. (2022). Measuring geopolitical risk. *American Economic Review*, 112(4), 1194–1225.
- Cox, D. R. (1972). Regression models and life-tables. *Journal of the Royal Statistical Society: Series B*, 34(2), 187–220.
- Diebold, F. X., & Mariano, R. S. (1995). Comparing predictive accuracy. *Journal of Business & Economic Statistics*, 13(3), 253–263.
- Glattfelder, J. B., Dupuis, A., & Olsen, R. B. (2011). Patterns in high-frequency FX data: Discovery of 12 empirical scaling laws. *Quantitative Finance*, 11(4), 599–614.
- Graf, E., Schmoor, C., Sauerbrei, W., & Schumacher, M. (1999). Assessment and comparison of prognostic classification schemes for survival data. *Statistics in Medicine*, 18(17–18), 2529–2545.
- Gu, S., Kelly, B., & Xiu, D. (2020). Empirical asset pricing via machine learning. *Review of Financial Studies*, 33(5), 2223–2273.
- Ishwaran, H., Kogalur, U. B., Blackstone, E. H., & Lauer, M. S. (2008). Random survival forests. *Annals of Applied Statistics*, 2(3), 841–860.
- Kvamme, H., Borgan, Ø., & Scheel, I. (2019). Time-to-event prediction with neural networks and Cox regression. *Journal of Machine Learning Research*, 20(129), 1–30.
- López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley.
- Uno, H., Cai, T., Pencina, M. J., D'Agostino, R. B., & Wei, L. J. (2011). On the C-statistics for evaluating overall adequacy of risk prediction procedures with censored survival data. *Statistics in Medicine*, 30(10), 1105–1117.

**Web sources used for market facts:** [World Bank on Vietnam's FTSE upgrade](https://www.worldbank.org/en/news/feature/2026/04/22/a-turning-point-for-viet-nam-s-capital-markets) · [Stockbiz on daily price limits](https://stockbiz.vn/en/learn/glossary/price-limits) · [FRED on S&P history](https://news.research.stlouisfed.org/2014/04/sp-series-update-2/) · [FRED on removing LBMA gold](https://news.research.stlouisfed.org/2022/01/ice-benchmark-administration-ltd-iba-data-to-be-removed-from-fred/) · [Geopolitical risk index](https://www.matteoiacoviello.com/gpr.htm)
