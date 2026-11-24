{{ config(order_by='(ticker, ex_date)') }}

-- Corporate actions used downstream: events inferred from CafeF (int_corporate_actions), with
-- verified facts (seed corporate_action_adjudications, D-007) replacing every inferred event
-- within 10 days of an adjudicated queue item.
--   verdict event_found    -> events rebuilt from facts (ratio from macro corporate_action_ratio)
--   verdict no_event_found -> the inferred event(s) near queue_date are dropped
--   verdict unclear        -> the inferred event is kept, status 'unadjudicated'
-- ex_date is moved to the stock's first trading day on or after the official ex-date.

with facts as (
    select * from {{ ref('corporate_action_adjudications') }}
),

resolved as (
    -- queue items with a definite answer
    select distinct ticker, queue_date
    from facts
    where verdict in ('event_found', 'no_event_found')
),

inferred as (
    select
        ca.ticker as ticker,
        ca.ex_date as ex_date,
        ca.adj_ratio as adj_ratio,
        if((ca.ticker, ca.ex_date) in (
                select ticker, queue_date from facts where verdict = 'unclear'
            ), 'unadjudicated', 'inferred') as status
    from {{ ref('int_corporate_actions') }} as ca
    where (ca.ticker, ca.ex_date) not in (
        select ca2.ticker, ca2.ex_date
        from {{ ref('int_corporate_actions') }} as ca2
        inner join resolved as r on ca2.ticker = r.ticker
        where abs(dateDiff('day', ca2.ex_date, r.queue_date)) <= 10
    )
),

fact_events as (
    select
        ticker,
        assumeNotNull(ex_date) as official_ex_date,
        sum(cash_vnd) as cash_vnd,
        sum(stock_ratio) as stock_ratio,
        sum(rights_ratio) as rights_ratio,
        max(rights_price_vnd) as rights_price_vnd,
        arrayStringConcat(groupUniqArray(source_url), ' ') as source_urls,
        min(confidence) as confidence
    from facts
    where verdict = 'event_found' and ex_date is not null
    group by ticker, official_ex_date
),

placed as (
    -- first trading day on or after the official ex-date
    select f.*, p.trade_date as ex_date
    from fact_events as f
    asof inner join (select ticker, trade_date from {{ ref('prices_daily_raw') }}) as p
        on f.ticker = p.ticker and p.trade_date >= f.official_ex_date
),

priced as (
    -- raw close on the last trading day before the (placed) ex-date
    select pl.*, p.close_vnd as prev_close
    from placed as pl
    asof inner join (
        select ticker, trade_date, close_vnd from {{ ref('prices_daily_raw') }}
    ) as p on pl.ticker = p.ticker and p.trade_date < pl.ex_date
)

select
    ticker,
    ex_date,
    adj_ratio,
    status,
    cast(null as Nullable(Date)) as official_ex_date,
    '' as source_urls
from inferred

union all

select
    ticker,
    ex_date,
    round({{ corporate_action_ratio('prev_close', 'cash_vnd', 'stock_ratio', 'rights_ratio',
                                    'rights_price_vnd') }}, 8) as adj_ratio,
    'adjudicated' as status,
    toNullable(official_ex_date) as official_ex_date,
    source_urls
from priced
