-- Every VN30 spell starting in the study period has a HOSE price row within 10 days of its
-- start (a wrong ticker or date would show up here). Documented holes in the CafeF history
-- (seed known_price_gaps) are excluded; any other gap fails.
select m.ticker, m.valid_from
from {{ ref('dim_vn30_membership') }} as m
where m.valid_from between '2012-02-06' and '2026-11-20'
  and (m.ticker, m.valid_from) not in (
      select m2.ticker, m2.valid_from
      from {{ ref('dim_vn30_membership') }} as m2
      inner join {{ ref('prices_daily_raw') }} as p on p.ticker = m2.ticker
      where p.exchange = 'HSX'
        and p.trade_date between m2.valid_from and addDays(m2.valid_from, 10)
  )
  and (m.ticker, m.valid_from) not in (
      select m3.ticker, m3.valid_from
      from {{ ref('dim_vn30_membership') }} as m3
      inner join {{ ref('known_price_gaps') }} as g on m3.ticker = g.ticker
      where m3.valid_from between g.gap_from and g.gap_to
  )
