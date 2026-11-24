{{ config(order_by='(exchange, trade_date)') }}

-- Trading sessions per exchange, inferred from the data: a date is a session when at least 20
-- ordinary shares on that exchange have a clean price row. session_no counts sessions, so the
-- number of sessions a stock missed between two of its rows is a difference of session_no.

select
    exchange,
    trade_date,
    count() as n_tickers,
    row_number() over (partition by exchange order by trade_date) as session_no
from {{ ref('prices_daily_raw') }}
group by exchange, trade_date
having n_tickers >= 20
