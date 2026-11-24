{{ config(order_by='(ticker, trade_date)') }}

-- Clean raw (unadjusted) daily prices of ordinary shares: one row per ticker per trading date.
-- Every row keeps its lineage back to the raw archive line it came from.

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
    toBool(warn_reason = 'ohlc_outside_range') as ohlc_outside_range,
    available_at_utc,
    raw_key,
    raw_sha256,
    source_file,
    row_num
from {{ ref('int_cafef__eod_checked') }}
where variant = 'raw'
  and instrument_type = 'share'
  and dq_outcome = 'kept'
