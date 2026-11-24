{# Cross-check of a corporate-action events model against Yahoo events (see
   qa_corporate_actions_vs_yahoo for the full description). events: a relation with
   ticker, ex_date, adj_ratio. #}
{% macro yahoo_comparison(events) %}

-- Cross-check of corporate actions inferred from CafeF (int_corporate_actions) against Yahoo
-- Finance events, for the Yahoo validation sample, within the study period and within each
-- symbol's Yahoo coverage.
--
-- Yahoo's expected ratio on ex-date d:  split(d) * P / (P - D)
--   split(d) = product of Yahoo split ratios on d (stock dividends appear as splits)
--   D        = Yahoo dividends on d, converted back to as-paid VND by multiplying with the
--              product of split ratios on or after d (Yahoo rescales dividends by later splits)
--   P        = our raw close on the last trading day before d
-- Each Yahoo event date is matched to our nearest event within 5 calendar days.
-- status: match (same date, ratios within 1%), ratio_mismatch, date_shift (nearby date),
--         yahoo_only, ours_only.

with yahoo_latest as (
    select *
    from {{ source('yahoo', 'raw_yahoo_events') }}
    where (ticker, fetched_at_utc) in (
        select ticker, max(fetched_at_utc) from {{ source('yahoo', 'raw_yahoo_events') }}
        group by ticker
    )
),

coverage as (
    select
        ticker,
        greatest(toDate('2012-01-03'), min(assumeNotNull(data_first_date))) as cov_from,
        least(toDate('2026-11-20'), max(assumeNotNull(data_last_date))) as cov_to
    from yahoo_latest
    where data_first_date is not null
    group by ticker
),

yahoo_days as (
    select
        ticker,
        ex_date,
        exp(sumIf(log(numerator / denominator), event_type = 'split')) as split_ratio,
        sumIf(amount, event_type = 'dividend') as div_rescaled
    from yahoo_latest
    where event_type in ('split', 'dividend')
    group by ticker, ex_date
),

yahoo_scaled as (
    select
        *,
        -- product of split ratios on or after this date
        exp(sum(log(split_ratio)) over (
            partition by ticker order by ex_date desc
            rows between unbounded preceding and current row
        )) as splits_on_or_after
    from yahoo_days
),

yahoo_expected as (
    select
        y.ticker as ticker,
        y.ex_date as yahoo_date,
        y.split_ratio as split_ratio,
        y.div_rescaled * y.splits_on_or_after as div_vnd,
        p.close_vnd as prev_close,
        y.split_ratio * p.close_vnd / (p.close_vnd - y.div_rescaled * y.splits_on_or_after)
            as yahoo_ratio
    from yahoo_scaled as y
    asof left join {{ ref('prices_daily_raw') }} as p
        on y.ticker = p.ticker and y.ex_date > p.trade_date
),

ours as (
    select ca.ticker, ca.ex_date as our_date, ca.adj_ratio as our_ratio
    from {{ events }} as ca
    inner join coverage as cv on ca.ticker = cv.ticker
    where ca.ex_date between cv.cov_from and cv.cov_to
),

yahoo_in_scope as (
    select ye.*
    from yahoo_expected as ye
    inner join coverage as cv on ye.ticker = cv.ticker
    where ye.yahoo_date between cv.cov_from and cv.cov_to
),

pairs as (
    select
        y.ticker as ticker,
        y.yahoo_date as yahoo_date,
        y.yahoo_ratio as yahoo_ratio,
        y.split_ratio as split_ratio,
        y.div_vnd as div_vnd,
        o.our_date as our_date,
        o.our_ratio as our_ratio,
        dateDiff('day', y.yahoo_date, o.our_date) as day_diff,
        row_number() over (
            partition by y.ticker, y.yahoo_date
            order by abs(dateDiff('day', y.yahoo_date, o.our_date)), o.our_date
        ) as rk
    from yahoo_in_scope as y
    inner join ours as o on y.ticker = o.ticker
    where abs(dateDiff('day', y.yahoo_date, o.our_date)) <= 5
),

yahoo_side as (
    select
        y.ticker as ticker,
        y.yahoo_date as yahoo_date,
        y.yahoo_ratio as yahoo_ratio,
        y.split_ratio as split_ratio,
        y.div_vnd as div_vnd,
        if(p.ticker = '', null, p.our_date) as our_date,
        if(p.ticker = '', null, p.our_ratio) as our_ratio,
        if(p.ticker = '', null, p.day_diff) as day_diff
    from yahoo_in_scope as y
    left join (select * from pairs where rk = 1) as p
        on y.ticker = p.ticker and y.yahoo_date = p.yahoo_date
),

ours_only as (
    select o.ticker, o.our_date, o.our_ratio
    from ours as o
    where (o.ticker, o.our_date) not in (
        select ticker, assumeNotNull(our_date) from yahoo_side where our_date is not null
    )
)

select
    ticker,
    toNullable(yahoo_date) as yahoo_date,
    toNullable(yahoo_ratio) as yahoo_ratio,
    toNullable(split_ratio) as split_ratio,
    toNullable(div_vnd) as div_vnd,
    our_date,
    our_ratio,
    day_diff,
    multiIf(
        our_date is null, 'yahoo_only',
        day_diff != 0, 'date_shift',
        abs(our_ratio / yahoo_ratio - 1) <= 0.01, 'match',
        'ratio_mismatch'
    ) as status
from yahoo_side

union all

select
    ticker,
    null, null, null, null,
    toNullable(our_date),
    toNullable(our_ratio),
    null,
    'ours_only'
from ours_only
{% endmacro %}
