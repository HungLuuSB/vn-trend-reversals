{{ config(
    order_by='(ticker, trade_date)',
    query_settings={'max_bytes_before_external_sort': 300000000, 'max_threads': 2}
) }}

-- Clean raw (unadjusted) daily prices of ordinary shares: one row per ticker per trading date.
-- price_source:
--   cafef_bulk    the pinned CafeF bulk archive (int_cafef__eod_checked, kept rows)
--   cafef_ticker  CafeF per-ticker history, used only inside documented bulk-archive gaps
--                 (seed known_price_gaps), with the gap's true exchange
-- Inside a gap, bulk rows that do exist keep their prices but take the gap's exchange (CafeF
-- labels pre-transfer days with the current exchange, e.g. LPB in 2017).
-- vwap_vnd / vwap_uncertainty_vnd come from the per-ticker history where it was fetched.
-- Every row keeps lineage back to the raw object and line/page it came from.

with gaps as (
    select ticker, gap_from, gap_to, exchange from {{ ref('known_price_gaps') }}
),

fills as (
    select * from {{ ref('int_price_gap_fills') }} where dq_outcome = 'kept'
),

bulk as (
    select
        ticker,
        trade_date,
        exchange,
        open_vnd,
        high_vnd,
        low_vnd,
        close_vnd,
        volume,
        -- D-002: open or close outside high-low; kept, flagged for robustness checks.
        warn_reason = 'ohlc_outside_range' as ohlc_outside_range,
        raw_key,
        raw_sha256,
        source_file,
        row_num
    from {{ ref('int_cafef__eod_checked') }}
    where variant = 'raw' and instrument_type = 'share' and dq_outcome = 'kept'
),

bulk_gap_exchange as (
    select b.ticker as ticker, b.trade_date as trade_date, any(g.exchange) as gap_exchange
    from bulk as b
    inner join gaps as g on b.ticker = g.ticker
    where b.trade_date between g.gap_from and g.gap_to
    group by b.ticker, b.trade_date
),

combined as (
    select
        b.ticker as ticker,
        b.trade_date as trade_date,
        if(x.gap_exchange = '', b.exchange, toLowCardinality(x.gap_exchange)) as exchange,
        b.open_vnd as open_vnd,
        b.high_vnd as high_vnd,
        b.low_vnd as low_vnd,
        b.close_vnd as close_vnd,
        b.volume as volume,
        b.ohlc_outside_range as ohlc_outside_range,
        b.raw_key as raw_key,
        b.raw_sha256 as raw_sha256,
        b.source_file as source_file,
        b.row_num as row_num,
        'cafef_bulk' as price_source
    from bulk as b
    left join bulk_gap_exchange as x on b.ticker = x.ticker and b.trade_date = x.trade_date
    where (b.ticker, b.trade_date) not in (select ticker, trade_date from fills)

    union all

    select
        ticker,
        trade_date,
        toLowCardinality(exchange),
        open_vnd,
        high_vnd,
        low_vnd,
        close_vnd,
        volume,
        ohlc_outside_range,
        raw_key,
        raw_sha256,
        toLowCardinality(page),
        toUInt32(row_in_page),
        'cafef_ticker'
    from fills
)

select
    c.ticker as ticker,
    c.trade_date as trade_date,
    toLowCardinality(toString(c.exchange)) as exchange,
    c.open_vnd as open_vnd,
    c.high_vnd as high_vnd,
    c.low_vnd as low_vnd,
    c.close_vnd as close_vnd,
    c.volume as volume,
    toBool(c.ohlc_outside_range) as ohlc_outside_range,
    -- When the day's prices became public: the session close, 15:00 Asia/Ho_Chi_Minh.
    toTimeZone(
        toDateTime64(concat(toString(c.trade_date), ' 15:00:00'), 3, 'Asia/Ho_Chi_Minh'), 'UTC'
    ) as available_at_utc,
    toLowCardinality(c.price_source) as price_source,
    h.vwap_vnd as vwap_vnd,
    h.vwap_uncertainty_vnd as vwap_uncertainty_vnd,
    c.raw_key as raw_key,
    c.raw_sha256 as raw_sha256,
    c.source_file as source_file,
    c.row_num as row_num
from combined as c
left join (
    select ticker, trade_date, toNullable(vwap_vnd) as vwap_vnd,
           toNullable(vwap_uncertainty_vnd) as vwap_uncertainty_vnd
    from {{ ref('stg_cafef_history') }}
) as h on c.ticker = h.ticker and c.trade_date = h.trade_date
