-- Missing values must be NULL, never NaN or +/-Inf (a NaN slips past "is null" checks and
-- into models). Covers the numeric feature columns of blocks C and D.
select 'local_market_daily' as model, trade_date
from {{ ref('local_market_daily') }}
where not isFinite(coalesce(vnindex_ret, 0)) or not isFinite(coalesce(vn30_ret, 0))
   or not isFinite(coalesce(advance_share, 0)) or not isFinite(coalesce(foreign_net_share, 0))
   or not isFinite(coalesce(vnindex_close, 0)) or not isFinite(coalesce(vn30_close, 0))
union all
select 'global_features_daily', trade_date
from {{ ref('global_features_daily') }}
where not isFinite(coalesce(spx_ret, 0)) or not isFinite(coalesce(nasdaq_ret, 0))
   or not isFinite(coalesce(dxy_ret, 0)) or not isFinite(coalesce(gold_ret, 0))
   or not isFinite(coalesce(brent_ret, 0)) or not isFinite(coalesce(hsi_ret, 0))
   or not isFinite(coalesce(sse_ret, 0)) or not isFinite(coalesce(usdvnd_ret, 0))
   or not isFinite(coalesce(usdcny_ret, 0)) or not isFinite(coalesce(vix_chg, 0))
   or not isFinite(coalesce(ust10_chg, 0)) or not isFinite(coalesce(gpr_chg, 0))
