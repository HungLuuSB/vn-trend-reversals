{{ config(
    order_by='(ticker, trade_date)',
    query_settings={'max_bytes_before_external_group_by': 300000000, 'max_threads': 2}
) }}

-- Raw and CafeF-adjusted prices side by side for ordinary shares, following the same source
-- choice as prices_daily_raw: the bulk archive, except inside documented gaps where the
-- per-ticker history fills in (research/DECISIONS.md D-006). adj_rounding_vnd is the maximum
-- rounding error of the adjusted price: the bulk archive publishes 4 decimals of thousand VND
-- (0.05 VND), the per-ticker history 2 decimals (5 VND).

with fills as (
    select ticker, trade_date
    from {{ ref('int_price_gap_fills') }}
    where dq_outcome = 'kept'
),

bulk as (
    select
        ticker,
        trade_date,
        anyIf(exchange, variant = 'raw') as exchange,
        anyIf(close_vnd, variant = 'raw') as raw_close,
        anyIf(low_vnd, variant = 'raw') as raw_low,
        anyIf(close_vnd, variant = 'adjusted') as adj_close,
        anyIf(low_vnd, variant = 'adjusted') as adj_low
    from {{ ref('int_cafef__eod_checked') }}
    where instrument_type = 'share' and dq_outcome = 'kept'
    group by ticker, trade_date
    having countIf(variant = 'raw') = 1 and countIf(variant = 'adjusted') = 1
)

select
    ticker,
    trade_date,
    exchange,
    raw_close,
    raw_low,
    adj_close,
    toNullable(adj_low) as adj_low,
    0.05 as adj_rounding_vnd,
    'cafef_bulk' as pair_source
from bulk
where (ticker, trade_date) not in (select ticker, trade_date from fills)

union all

select
    ticker,
    trade_date,
    toLowCardinality(exchange),
    close_vnd,
    low_vnd,
    adj_close_vnd,
    null,  -- the per-ticker history has no adjusted low
    5.0,
    'cafef_ticker'
from {{ ref('int_price_gap_fills') }}
where dq_outcome = 'kept' and adj_close_vnd > 0
