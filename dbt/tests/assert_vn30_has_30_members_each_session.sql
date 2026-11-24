-- From the launch (2012-02-06) on, every HOSE session in the study period has exactly 30
-- VN30 members; before the launch, none.
select trade_date, countIf(in_vn30) as n_members
from {{ ref('research_universe_daily') }}
group by trade_date
having (trade_date >= '2012-02-06' and n_members != 30)
    or (trade_date < '2012-02-06' and n_members != 0)
