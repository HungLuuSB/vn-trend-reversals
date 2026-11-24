{{ config(order_by='(ticker)') }}

-- Where both CafeF sources have a stock-day (raw bulk archive, kept rows; per-ticker history),
-- how often do they agree? A gap fill is trusted only if this agreement is high.

select
    h.ticker as ticker,
    count() as n_overlap,
    countIf(h.close_vnd = b.close_vnd) as close_equal,
    countIf(h.open_vnd = b.open_vnd and h.high_vnd = b.high_vnd and h.low_vnd = b.low_vnd
            and h.close_vnd = b.close_vnd) as ohlc_equal,
    countIf(h.volume = b.volume) as volume_equal,
    round(close_equal / n_overlap, 4) as close_equal_rate,
    round(ohlc_equal / n_overlap, 4) as ohlc_equal_rate,
    round(volume_equal / n_overlap, 4) as volume_equal_rate,
    min(h.trade_date) as first_date,
    max(h.trade_date) as last_date
from {{ ref('stg_cafef_history') }} as h
inner join (
    select ticker, trade_date, open_vnd, high_vnd, low_vnd, close_vnd, volume
    from {{ ref('int_cafef__eod_checked') }}
    where variant = 'raw' and dq_outcome = 'kept'
) as b on h.ticker = b.ticker and h.trade_date = b.trade_date
group by h.ticker
