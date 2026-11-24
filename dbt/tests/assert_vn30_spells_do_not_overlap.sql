-- A stock cannot be added while already a member: membership spells must not overlap.
select a.ticker, a.valid_from, b.valid_from
from {{ ref('dim_vn30_membership') }} as a
inner join {{ ref('dim_vn30_membership') }} as b on a.ticker = b.ticker
where a.valid_from < b.valid_from
  and (a.valid_to is null or assumeNotNull(a.valid_to) >= b.valid_from)
