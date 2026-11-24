{{ config(order_by='(reject_reason, variant, ticker, trade_date)') }}

-- Quarantine: every row that failed a quality check, with the reason. Rows here never reach
-- prices_daily_raw. Kept for review, never silently deleted.

select
    reject_reason,
    variant,
    instrument_type,
    exchange,
    ticker,
    trade_date,
    open_vnd,
    high_vnd,
    low_vnd,
    close_vnd,
    volume,
    n_rows,
    n_versions,
    n_exchanges,
    raw_key,
    source_file,
    row_num
from {{ ref('int_cafef__eod_checked') }}
where dq_outcome = 'rejected'
