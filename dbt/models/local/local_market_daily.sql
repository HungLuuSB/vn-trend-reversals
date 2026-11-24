{{ config(materialized='table', order_by='(trade_date)') }}

-- Feature block C (docs/proposal.md; research/DECISIONS.md D-009): local market state, one row
-- per HOSE session d. Every value describes the PREVIOUS HOSE session (its close, public at
-- 15:00 Asia/Ho_Chi_Minh) so it is known before the 09:00 decision on d (CLAUDE.md rule 4).
--   VN-Index / VN30 index: close and log return (CafeF per-ticker history)
--   breadth: HOSE ordinary shares up / down / unchanged on ADJUSTED close-to-close returns
--            (raw returns would count ex-dividend days as declines)
--   turnover: VN-Index matched value (billion VND)
--   foreign: HOSE market foreign net buying (VND) and as a share of matched value
-- The VN-Index swing state is computed with the swing labeller from the snapshot.

with sessions as (
    select trade_date from {{ ref('int_trading_sessions') }} where exchange = 'HSX'
),

idx as (
    select
        trade_date,
        -- OrNull: a session without a value must be NULL, not 0 (VN30 starts 2012-02-06)
        anyIfOrNull(close_vnd / 1000, ticker = 'VNINDEX') as vnindex_close,
        anyIfOrNull(close_vnd / 1000, ticker = 'VN30INDEX') as vn30_close,
        anyIfOrNull(value_bn, ticker = 'VNINDEX') as hose_matched_value_bn
    from {{ ref('stg_cafef_history') }}
    where ticker in ('VNINDEX', 'VN30INDEX')
    group by trade_date
),

rets as (
    select
        trade_date,
        close_adj / lagInFrame(close_adj) over w - 1 as r,
        row_number() over w as rn
    from {{ ref('prices_daily_adjusted') }}
    where exchange = 'HSX'
    window w as (partition by ticker order by trade_date rows between 1 preceding and current row)
),

breadth as (
    select
        trade_date,
        countIf(r > 1e-9) as n_up,
        countIf(r < -1e-9) as n_down,
        countIf(abs(r) <= 1e-9) as n_unchanged
    from rets
    where rn > 1
    group by trade_date
),

foreign as (
    select trade_date, any(net_value_vnd) as foreign_net_value_vnd
    from {{ source('cafef_history', 'raw_cafef_foreign') }}
    where ticker = 'VNINDEX'
    group by trade_date
),

per_session as (
    select
        s.trade_date as trade_date,
        if(i.trade_date = toDate('1970-01-01'), null, i.vnindex_close) as vnindex_close,
        if(i.trade_date = toDate('1970-01-01'), null, i.vn30_close) as vn30_close,
        if(i.trade_date = toDate('1970-01-01'), null, i.hose_matched_value_bn)
            as hose_matched_value_bn,
        b.n_up as n_up,
        b.n_down as n_down,
        b.n_unchanged as n_unchanged,
        if(f.trade_date = toDate('1970-01-01'), null, toNullable(f.foreign_net_value_vnd))
            as foreign_net_value_vnd
    from sessions as s
    left join idx as i on s.trade_date = i.trade_date
    left join breadth as b on s.trade_date = b.trade_date
    left join foreign as f on s.trade_date = f.trade_date
),

with_returns as (
    select
        *,
        log(vnindex_close / lagInFrame(vnindex_close) over w) as vnindex_ret,
        log(vn30_close / lagInFrame(vn30_close) over w) as vn30_ret
    from per_session
    window w as (order by trade_date rows between 1 preceding and current row)
),

lagged as (
    -- previous session's values, under distinct names so no alias shadows a source column
    select
        trade_date,
        lagInFrame(trade_date) over w as source_session,
        lagInFrame(vnindex_close) over w as p_vnindex_close,
        lagInFrame(vnindex_ret) over w as p_vnindex_ret,
        lagInFrame(vn30_close) over w as p_vn30_close,
        lagInFrame(vn30_ret) over w as p_vn30_ret,
        lagInFrame(n_up) over w as p_n_up,
        lagInFrame(n_down) over w as p_n_down,
        lagInFrame(n_unchanged) over w as p_n_unchanged,
        lagInFrame(hose_matched_value_bn) over w as p_matched_value_bn,
        lagInFrame(foreign_net_value_vnd) over w as p_foreign_net_value_vnd,
        row_number() over w as rn
    from with_returns
    window w as (order by trade_date rows between 1 preceding and current row)
)

select
    trade_date,
    toTimeZone(
        toDateTime64(concat(toString(trade_date), ' 09:00:00'), 3, 'Asia/Ho_Chi_Minh'), 'UTC'
    ) as decision_time_utc,
    source_session,
    toTimeZone(
        toDateTime64(concat(toString(source_session), ' 15:00:00'), 3, 'Asia/Ho_Chi_Minh'), 'UTC'
    ) as available_at_utc,
    p_vnindex_close as vnindex_close,
    p_vnindex_ret as vnindex_ret,
    p_vn30_close as vn30_close,
    p_vn30_ret as vn30_ret,
    p_n_up as n_up,
    p_n_down as n_down,
    p_n_unchanged as n_unchanged,
    p_n_up / nullIf(p_n_up + p_n_down, 0) as advance_share,
    p_matched_value_bn as hose_matched_value_bn,
    p_foreign_net_value_vnd as foreign_net_value_vnd,
    p_foreign_net_value_vnd / nullIf(p_matched_value_bn * 1e9, 0) as foreign_net_share
from lagged
where rn > 1
