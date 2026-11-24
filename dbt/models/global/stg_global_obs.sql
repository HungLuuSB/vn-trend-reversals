-- depends_on: {{ ref('global_series') }}
-- One row per (series, obs_date): the latest fetch wins. Bars dated on or after their fetch
-- date are dropped (possibly incomplete intraday bars). available_at_utc follows seed
-- global_series (D-009).

with ranked as (
    select
        o.*,
        s.series_id as series_id,
        s.kind as kind,
        row_number() over (
            partition by o.symbol, o.obs_date order by o.fetched_at_utc desc, o.raw_key desc
        ) as rk
    from {{ source('global', 'raw_global_obs') }} as o
    inner join {{ ref('global_series') }} as s on o.symbol = s.symbol
    where o.obs_date < toDate(o.fetched_at_utc)
)

select
    series_id,
    symbol,
    kind,
    obs_date,
    close as value,
    {{ global_available_at('series_id', 'obs_date') }} as available_at_utc,
    toLowCardinality(raw_key) as raw_key,
    fetched_at_utc
from ranked
where rk = 1
