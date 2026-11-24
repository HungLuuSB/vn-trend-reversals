-- Every clean row: positive prices, low <= open/close <= high, volume >= 0, weekday.
select *
from {{ ref('prices_daily_raw') }}
where least(open_vnd, high_vnd, low_vnd, close_vnd) <= 0
   or high_vnd < low_vnd
   or open_vnd > high_vnd or open_vnd < low_vnd
   or close_vnd > high_vnd or close_vnd < low_vnd
   or volume < 0
   or toDayOfWeek(trade_date) >= 6
