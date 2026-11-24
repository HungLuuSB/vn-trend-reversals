-- available_at_utc must be 15:00 Asia/Ho_Chi_Minh (08:00 UTC, no DST) on the trade date itself,
-- never earlier: a value cannot be public before its session closes.
select ticker, trade_date, available_at_utc
from {{ ref('prices_daily_raw') }}
where toDate(available_at_utc, 'Asia/Ho_Chi_Minh') != trade_date
   or formatDateTime(available_at_utc, '%H:%i:%S', 'Asia/Ho_Chi_Minh') != '15:00:00'
   or formatDateTime(available_at_utc, '%H:%i:%S', 'UTC') != '08:00:00'
