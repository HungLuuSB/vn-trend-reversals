-- Every clean row: positive prices, low <= high, volume >= 0, weekday.
-- Open or close outside low..high is allowed only when flagged (research/paper1/DECISIONS.md D-002),
-- and the flag must be set exactly on those rows.
select *
from {{ ref('prices_daily_raw') }}
where least(open_vnd, high_vnd, low_vnd, close_vnd) <= 0
   or high_vnd < low_vnd
   or volume < 0
   or toDayOfWeek(trade_date) >= 6
   or ohlc_outside_range != (
        open_vnd > high_vnd or open_vnd < low_vnd
        or close_vnd > high_vnd or close_vnd < low_vnd
      )
