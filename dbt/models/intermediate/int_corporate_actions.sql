{{ config(
    order_by='(ticker, ex_date)',
    query_settings={'max_bytes_before_external_sort': 300000000, 'max_threads': 2}
) }}

-- Corporate actions (cash dividends, stock dividends, bonus shares, splits, rights) inferred
-- from CafeF: on an ex-date the ratio f = adjusted / raw jumps. For trading day t after
-- trading day t-1:
--
--     adj_ratio = f(t) / f(t-1)  =  previous raw close / theoretical ex-date reference price
--
-- e.g. 1.25 for a 25% stock dividend, 10000 / 9500 = 1.0526 for a 500 VND cash dividend on a
-- 10,000 VND close. Adjusted prices are rounded (bulk archive: 0.05 VND; per-ticker history,
-- used inside documented gaps: 5 VND); a jump counts as an event only when it exceeds
-- max(0.1%, 4x the relative rounding error of the two adjusted prices). In gap periods this
-- can miss cash dividends below roughly 1% of the price. If a stock does not trade on its ex-date, the
-- event lands on its next trading day (ex_date = first trading day on or after the true one).

with series as (
    select
        *,
        adj_close / raw_close as f,
        lagInFrame(adj_close / raw_close) over w as f_prev,
        lagInFrame(adj_low / raw_low) over w as f_low_prev,
        lagInFrame(raw_close) over w as raw_prev_close,
        lagInFrame(adj_close) over w as adj_prev_close,
        lagInFrame(adj_rounding_vnd) over w as adj_prev_rounding_vnd,
        lagInFrame(trade_date) over w as prev_trade_date,
        row_number() over w as rn
    from {{ ref('int_cafef__raw_adj_pairs') }}
    window w as (partition by ticker order by trade_date rows between 1 preceding and current row)
),

ratios as (
    select
        ticker,
        exchange,
        trade_date as ex_date,
        prev_trade_date,
        f / f_prev as adj_ratio,
        (adj_low / raw_low) / f_low_prev as adj_ratio_low,
        greatest(0.001, 4 * (adj_rounding_vnd / adj_close + adj_prev_rounding_vnd / adj_prev_close))
            as noise_tol,
        pair_source,
        raw_prev_close,
        raw_close,
        raw_close / raw_prev_close as raw_gap,
        dateDiff('day', prev_trade_date, trade_date) as gap_days
    from series
    where rn > 1
)

select
    *,
    -- The ratio from daily lows should agree with the one from closes; disagreement means the
    -- event is less certain (e.g. CafeF rounding on very low adjusted prices).
    -- NULL when the source has no adjusted low (per-ticker history)
    abs(adj_ratio_low / adj_ratio - 1) <= 2 * noise_tol as low_close_agree,
    -- After more than 30 calendar days without trading (suspension, relisting) the jump mixes
    -- the event with the price change over the gap; treat such events as uncertain.
    gap_days > 30 as after_long_gap
from ratios
where abs(adj_ratio - 1) > noise_tol
