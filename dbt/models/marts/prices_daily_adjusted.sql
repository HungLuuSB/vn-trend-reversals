{{ config(
    order_by='(ticker, trade_date)',
    query_settings={'max_bytes_before_external_sort': 300000000, 'max_threads': 2}
) }}

-- Our own back-adjusted prices (CLAUDE.md rule 7): raw prices divided by the product of the
-- adjustment ratios of every corporate action AFTER the trade date (int_corporate_actions).
-- The latest prices equal raw prices; earlier prices are scaled down.
--
-- LOOK-AHEAD WARNING. Back-adjustment rescales a day's price by events that happen later.
-- Returns and scale-free ratios (e.g. ATR20 / price) are unaffected, because every price in a
-- window is scaled by the same factor unless an event falls inside the window, and such an
-- event's ex-date is already public. Price LEVELS are not: use prices_daily_raw for anything
-- that depends on a level (tick size, price bands, low-price filters).
-- Volume is not adjusted (the split share of each event is unknown).

with marked as (
    select
        p.*,
        if(ca.ticker = '', 0, log(ca.adj_ratio)) as log_ratio
    from {{ ref('prices_daily_raw') }} as p
    left join {{ ref('int_corporate_actions_final') }} as ca
        on p.ticker = ca.ticker and p.trade_date = ca.ex_date
),

factored as (
    select
        *,
        -- Sum of log ratios of events strictly after this date.
        sum(log_ratio) over (
            partition by ticker order by trade_date desc
            rows between unbounded preceding and 1 preceding
        ) as log_after
    from marked
)

select
    ticker,
    trade_date,
    exchange,
    -- Rounded to 1e-4 VND (far below any tick) so results are exactly reproducible.
    round(exp(-log_after), 8) as adj_factor,  -- ClickHouse exp/log carry ~1e-9 relative error
    round(open_vnd * exp(-log_after), 4) as open_adj,
    round(high_vnd * exp(-log_after), 4) as high_adj,
    round(low_vnd * exp(-log_after), 4) as low_adj,
    round(close_vnd * exp(-log_after), 4) as close_adj,
    close_vnd as close_raw,
    volume,
    ohlc_outside_range,
    available_at_utc
from factored
