{{ config(
    order_by='(variant, ticker, trade_date, row_num)',
    query_settings={
        'max_bytes_before_external_sort': 300000000,
        'max_bytes_before_external_group_by': 300000000,
        'max_threads': 2
    }
) }}

-- Every staged row with its quality verdict. Nothing is dropped: each row ends in exactly one
-- dq_outcome (kept, duplicate_copy or rejected), so counts reconcile with staging.
-- Warnings (warn_reason) do not reject a row; they travel with it as a flag.
--
-- Group statistics use window functions (no self-join). The windows' PARTITION BY / ORDER BY
-- match raw_cafef_eod's sorting key (variant, ticker, trade_date, exchange, row_num), so
-- ClickHouse can stream rows in order instead of holding all of them in memory.

with windowed as (
    select
        *,
        count() over g as n_rows,
        uniqExact(tuple(open_vnd, high_vnd, low_vnd, close_vnd, volume)) over g as n_versions,
        uniqExact(exchange) over g as n_exchanges,
        row_number() over g_ordered as copy_rank
    from {{ ref('stg_cafef__eod') }}
    window
        g as (partition by variant, ticker, trade_date),
        g_ordered as (partition by variant, ticker, trade_date order by exchange, row_num)
),

flagged as (
    select
        *,
        -- Rejecting checks; first failure wins. Listed in models/intermediate/_intermediate.yml.
        multiIf(
            instrument_type = 'invalid', 'invalid_ticker',
            n_versions > 1, 'conflicting_duplicate',
            n_exchanges > 1, 'exchange_conflict',
            least(open_vnd, high_vnd, low_vnd, close_vnd) <= 0, 'nonpositive_price',
            high_vnd < low_vnd, 'high_below_low',
            volume < 0, 'negative_volume',
            toDayOfWeek(trade_date) >= 6, 'weekend',
            ''
        ) as reject_reason,
        -- Warning only (research/paper1/DECISIONS.md D-002): open or close outside the day's high-low,
        -- most likely auction prices outside the continuous session. The row is kept.
        if(
            open_vnd > high_vnd or open_vnd < low_vnd
                or close_vnd > high_vnd or close_vnd < low_vnd,
            'ohlc_outside_range',
            ''
        ) as warn_reason
    from windowed
)

select
    *,
    multiIf(
        reject_reason != '', 'rejected',
        copy_rank > 1, 'duplicate_copy',
        'kept'
    ) as dq_outcome
from flagged
