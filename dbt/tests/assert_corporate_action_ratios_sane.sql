-- Every inferred event has a positive, finite ratio within a plausible range
-- (0.1x .. 20x covers reverse splits up to 10:1 and bonus issues up to 1,900%).
-- Events after a long trading gap are excluded: their jump includes the price change over
-- the gap (e.g. PTG after 695 days, VNX after 181 days), so they are flagged instead.
select *
from {{ ref('int_corporate_actions') }}
where not isFinite(adj_ratio)
   or (not after_long_gap and (adj_ratio <= 0.1 or adj_ratio >= 20))
