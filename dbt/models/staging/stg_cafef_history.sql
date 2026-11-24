-- CafeF per-ticker history, one row per (ticker, trade_date): the most recent fetch wins.
-- Prices in VND. vwap_vnd = matched value / matched volume; matched value is published in
-- billion VND with 2 decimals, so the VWAP is uncertain by up to 0.005e9 / volume VND.

with ranked as (
    select
        *,
        row_number() over (
            partition by ticker, trade_date order by fetched_at_utc desc, raw_key desc
        ) as rk
    from {{ source('cafef_history', 'raw_cafef_history') }}
)

select
    ticker,
    trade_date,
    purpose,
    round(open * 1000, 4) as open_vnd,
    round(high * 1000, 4) as high_vnd,
    round(low * 1000, 4) as low_vnd,
    round(close * 1000, 4) as close_vnd,
    round(adj_close * 1000, 4) as adj_close_vnd,
    volume,
    value_bn,
    if(volume > 0, value_bn * 1e9 / volume, null) as vwap_vnd,
    if(volume > 0, 0.005e9 / volume, null) as vwap_uncertainty_vnd,
    pt_volume,
    pt_value_bn,
    toLowCardinality(raw_key) as raw_key,
    toLowCardinality(raw_sha256) as raw_sha256,
    page,
    row_in_page,
    fetched_at_utc
from ranked
where rk = 1
