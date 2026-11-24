-- prices_daily_raw must have exactly one row per ticker and trading date.
select ticker, trade_date, count() as n
from {{ ref('prices_daily_raw') }}
group by ticker, trade_date
having n > 1
