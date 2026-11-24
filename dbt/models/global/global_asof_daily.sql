{{ config(materialized='table', order_by='(series_id, trade_date)') }}

-- For every HOSE session and every global series: the latest value that was public before the
-- 09:00 Asia/Ho_Chi_Minh decision time of that session (CLAUDE.md rule 4). Series with no
-- value yet (e.g. before the series starts) have no row.

with sessions as (
    select
        trade_date,
        toTimeZone(
            toDateTime64(concat(toString(trade_date), ' 09:00:00'), 3, 'Asia/Ho_Chi_Minh'), 'UTC'
        ) as decision_time_utc
    from {{ ref('int_trading_sessions') }}
    where exchange = 'HSX'
),

grid as (
    select s.trade_date, s.decision_time_utc, g.series_id
    from sessions as s
    cross join (select series_id from {{ ref('global_series') }}) as g
)

select
    g.trade_date as trade_date,
    g.decision_time_utc as decision_time_utc,
    g.series_id as series_id,
    o.obs_date as obs_date,
    o.value as value,
    o.available_at_utc as available_at_utc,
    dateDiff('day', o.obs_date, g.trade_date) as staleness_days,
    o.raw_key as raw_key
from grid as g
asof inner join {{ ref('stg_global_obs') }} as o
    on g.series_id = o.series_id and o.available_at_utc < g.decision_time_utc
