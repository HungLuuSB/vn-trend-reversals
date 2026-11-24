-- Where limits are computed: positive reference, floor < reference < ceiling, prices on ticks.
select ticker, trade_date, ref_price, floor_price, ceiling_price
from {{ ref('prices_daily_limits') }}
where limit_status = 'computed'
  and not (ref_price > 0 and floor_price > 0 and floor_price < ref_price and ref_price < ceiling_price)
