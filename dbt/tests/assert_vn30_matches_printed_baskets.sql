-- Every full basket printed in a source (seed vn30_baskets) equals the membership rebuilt
-- from vn30_changes on that date. Returns tickers in one set but not the other.
with printed as (
    select effective_date as d, ticker from {{ ref('vn30_baskets') }}
),
rebuilt as (
    select p.d as d, m.ticker as ticker
    from (select distinct d from printed) as p
    cross join {{ ref('dim_vn30_membership') }} as m
    where p.d >= m.valid_from and (m.valid_to is null or p.d <= assumeNotNull(m.valid_to))
)
select d, ticker, 'printed_only' as side from printed
where (d, ticker) not in (select d, ticker from rebuilt)
union all
select d, ticker, 'rebuilt_only' from rebuilt
where (d, ticker) not in (select d, ticker from printed)
