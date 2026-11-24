-- Our adjusted prices must reproduce CafeF's adjusted file up to one constant per ticker
-- (CafeF sometimes applies an event dated after a stock's last trade to the whole series,
-- which changes no return). Fails if more than 100 study-period rows differ by > 0.5% after
-- per-ticker scale normalisation (2026-11-24 baseline: 17 rows, one ticker).
{{ config(severity='error') }}

with m as (
    select a.ticker, a.trade_date, a.close_adj / c.close_vnd as q
    from {{ ref('prices_daily_adjusted') }} as a
    inner join (
        select ticker, trade_date, close_vnd
        from {{ ref('int_cafef__eod_checked') }}
        where variant = 'adjusted' and instrument_type = 'share' and dq_outcome = 'kept'
    ) as c using (ticker, trade_date)
    where a.trade_date between '2012-01-03' and '2026-11-20'
),

n as (
    select ticker, abs(q / median(q) over (partition by ticker) - 1) as dn from m
)

select count() as n_off
from n
where dn > 0.005
having n_off > 100
