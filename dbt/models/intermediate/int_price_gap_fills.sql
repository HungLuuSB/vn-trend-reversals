{{ config(order_by='(ticker, trade_date)') }}

-- Per-ticker history rows that fall inside a documented gap of the bulk archive (seed
-- known_price_gaps), with the gap's true exchange and the same rejecting checks as the bulk
-- rows (int_cafef__eod_checked). Only dq_outcome = 'kept' rows reach prices_daily_raw.

with fills as (
    select
        h.*,
        g.exchange as exchange
    from {{ ref('stg_cafef_history') }} as h
    inner join {{ ref('known_price_gaps') }} as g on h.ticker = g.ticker
    where h.trade_date between g.gap_from and g.gap_to
)

select
    *,
    multiIf(
        least(open_vnd, high_vnd, low_vnd, close_vnd) <= 0, 'nonpositive_price',
        high_vnd < low_vnd, 'high_below_low',
        volume < 0, 'negative_volume',
        toDayOfWeek(trade_date) >= 6, 'weekend',
        ''
    ) as reject_reason,
    if(reject_reason = '', 'kept', 'rejected') as dq_outcome,
    open_vnd > high_vnd or open_vnd < low_vnd
        or close_vnd > high_vnd or close_vnd < low_vnd as ohlc_outside_range
from fills
