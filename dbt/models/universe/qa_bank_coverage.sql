{{ config(materialized='table', order_by='(ticker, first_trade_date)') }}

-- Price coverage of every bank exchange spell (seed bank_spells) inside the study period:
-- expected = HOSE sessions in the spell; got = clean CafeF rows on the spell's exchange.
-- CafeF drops a stock's history from before an exchange move, so pre-transfer spells (e.g.
-- ACB and SHB on HNX) show little or no coverage. Reported in the paper's data section.

{% set study_start = '2012-01-03' %}
{% set study_end = '2026-11-20' %}

with spells as (
    select
        ticker,
        exchange,
        first_trade_date,
        last_trade_date,
        greatest(first_trade_date, toDate('{{ study_start }}')) as from_date,
        least(coalesce(last_trade_date, toDate('{{ study_end }}')), toDate('{{ study_end }}'))
            as to_date,
        end_reason,
        confidence
    from {{ ref('bank_spells') }}
),

expected as (
    select sp.ticker, sp.first_trade_date, count() as expected_sessions
    from spells as sp
    cross join (
        select trade_date from {{ ref('int_trading_sessions') }} where exchange = 'HSX'
    ) as s
    where s.trade_date between sp.from_date and sp.to_date
    group by sp.ticker, sp.first_trade_date
),

got as (
    select sp.ticker, sp.first_trade_date,
        countIf(p.exchange = sp.exchange) as rows_on_exchange,
        countIf(p.exchange != sp.exchange) as rows_mislabelled
    from spells as sp
    inner join {{ ref('prices_daily_raw') }} as p on sp.ticker = p.ticker
    where p.trade_date between sp.from_date and sp.to_date
    group by sp.ticker, sp.first_trade_date
)

select
    sp.ticker as ticker,
    sp.exchange as exchange,
    sp.first_trade_date as first_trade_date,
    sp.last_trade_date as last_trade_date,
    sp.from_date as study_from,
    sp.to_date as study_to,
    coalesce(e.expected_sessions, 0) as expected_sessions,
    coalesce(g.rows_on_exchange, 0) as rows_on_exchange,
    coalesce(g.rows_mislabelled, 0) as rows_mislabelled,
    if(expected_sessions = 0, null, rows_on_exchange / expected_sessions) as coverage,
    sp.end_reason as end_reason,
    sp.confidence as confidence
from spells as sp
left join expected as e on sp.ticker = e.ticker and sp.first_trade_date = e.first_trade_date
left join got as g on sp.ticker = g.ticker and sp.first_trade_date = g.first_trade_date
where sp.from_date <= sp.to_date
