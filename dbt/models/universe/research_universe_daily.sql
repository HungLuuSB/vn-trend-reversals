{{ config(
    materialized='table',
    order_by='(trade_date, ticker)',
    query_settings={'max_threads': 2}
) }}

-- The research universe (CLAUDE.md, Paper 1): VN30 members as of each date plus all listed
-- banks, on every HOSE session of the study period (research/DECISIONS.md D-001).
-- One row per (session, ticker) in the universe, whether or not the stock traded that day,
-- so suspensions stay visible (has_price = false).

{% set study_start = '2012-01-03' %}
{% set study_end = '2026-11-20' %}

with sessions as (
    select trade_date
    from {{ ref('int_trading_sessions') }}
    where exchange = 'HSX' and trade_date between '{{ study_start }}' and '{{ study_end }}'
),

vn30 as (
    select s.trade_date as trade_date, m.ticker as ticker
    from sessions as s
    cross join {{ ref('dim_vn30_membership') }} as m
    where s.trade_date >= m.valid_from
      and (m.valid_to is null or s.trade_date <= assumeNotNull(m.valid_to))
),

banks as (
    select s.trade_date as trade_date, b.ticker as ticker, b.exchange as bank_exchange
    from sessions as s
    cross join {{ ref('bank_spells') }} as b
    where s.trade_date >= b.first_trade_date
      and (b.last_trade_date is null or s.trade_date <= assumeNotNull(b.last_trade_date))
),

members as (
    select
        trade_date,
        ticker,
        max(in_vn30) as in_vn30,
        max(is_bank) as is_bank,
        anyIf(bank_exchange, bank_exchange != '') as bank_exchange
    from (
        select trade_date, ticker, 1 as in_vn30, 0 as is_bank, '' as bank_exchange from vn30
        union all
        select trade_date, ticker, 0, 1, bank_exchange from banks
    )
    group by trade_date, ticker
)

select
    m.trade_date as trade_date,
    m.ticker as ticker,
    toBool(m.in_vn30) as in_vn30,
    toBool(m.is_bank) as is_bank,
    -- exchange of the bank's listing spell that day (true exchange, from bank_spells)
    if(m.bank_exchange = '', null, toNullable(m.bank_exchange)) as bank_exchange,
    -- D-005: banks registered on UPCoM (not listed on HOSE/HNX) are kept but flagged so the
    -- main results can be checked without them.
    toBool(m.is_bank = 1 and m.bank_exchange = 'UPCOM') as bank_on_upcom,
    p.ticker != '' as has_price,
    -- exchange label in the CafeF row (can be wrong for pre-transfer days, e.g. LPB in 2017)
    if(p.ticker = '', null, toNullable(p.exchange)) as cafef_exchange
from members as m
left join {{ ref('prices_daily_raw') }} as p
    on m.ticker = p.ticker and m.trade_date = p.trade_date
