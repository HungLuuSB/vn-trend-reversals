{{ config(materialized='table', order_by='(ticker, valid_from)') }}

-- One row per VN30 membership spell: valid_from = effective date of the addition (or launch),
-- valid_to = last day before the effective date of the removal (NULL while still a member).
-- Point in time: a stock is a member on date d iff valid_from <= d <= coalesce(valid_to, d).

with entries as (
    select ticker, effective_date, announcement_date, source_url, confidence
    from {{ ref('vn30_changes') }}
    where action in ('initial', 'add')
),

exits as (
    select ticker, effective_date as exit_date, announcement_date as exit_announced
    from {{ ref('vn30_changes') }}
    where action = 'remove'
)

select
    e.ticker as ticker,
    e.effective_date as valid_from,
    if(x.exit_date = toDate('1970-01-01'), null, toNullable(x.exit_date - 1)) as valid_to,
    e.announcement_date as entry_announced,
    if(x.exit_date = toDate('1970-01-01'), null, x.exit_announced) as exit_announced,
    e.source_url as entry_source_url,
    e.confidence as entry_confidence
from entries as e
asof left join exits as x
    on e.ticker = x.ticker and e.effective_date < x.exit_date
