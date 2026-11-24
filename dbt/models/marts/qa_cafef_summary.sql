{{ config(materialized='view') }}

-- Row counts by quality outcome: the data-quality report for the pinned CafeF archives.

select
    variant,
    instrument_type,
    dq_outcome,
    reject_reason,
    warn_reason,
    count() as n_rows,
    uniqExact(ticker) as n_tickers,
    min(trade_date) as first_date,
    max(trade_date) as last_date
from {{ ref('int_cafef__eod_checked') }}
group by variant, instrument_type, dq_outcome, reject_reason, warn_reason
order by variant, instrument_type, dq_outcome, reject_reason, warn_reason
