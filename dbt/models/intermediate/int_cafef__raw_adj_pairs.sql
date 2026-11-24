{{ config(
    order_by='(ticker, trade_date)',
    query_settings={'max_bytes_before_external_group_by': 300000000, 'max_threads': 2}
) }}

-- Raw and CafeF-adjusted prices side by side, for ordinary shares where both rows passed the
-- quality checks. Input to corporate-action inference (int_corporate_actions).

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
