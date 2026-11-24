-- depends_on: {{ ref('price_limit_schedule') }}
-- depends_on: {{ ref('tick_size_schedule') }}
-- depends_on: {{ ref('reference_price_rule') }}
{{ config(
    order_by='(ticker, trade_date)',
    query_settings={
        'max_bytes_before_external_sort': 300000000,
        'max_bytes_before_external_group_by': 300000000,
        'max_threads': 2
    }
) }}

-- Exchange reference price, daily ceiling/floor and limit hits per stock-day (CLAUDE.md rule 6,
-- research/DECISIONS.md D-003). All levels use RAW prices.
--
-- reference = previous close, divided by the corporate-action ratio on ex-dates
--             (only where the exchange's rule was prev_close: HOSE always, HNX from 2013-07-29;
--              HNX before that and UPCoM used a VWAP that CafeF does not publish)
-- ceiling   = reference * (1 + limit), rounded DOWN to the tick of its price level
-- floor     = reference * (1 - limit), rounded UP to the tick of its price level
--             (rounding toward the reference: explicit in the rules from 2021, assumed before)
-- If rounding makes ceiling <= reference (or floor >= reference), use reference +/- 1 tick.
--
-- regime: normal; resumption (> 25 sessions missed); new_listing (first row); exchange_transfer
-- limit_status: computed | ref_not_reconstructable | special_regime_unknown

with base as (
    select
        ticker,
        trade_date,
        exchange,
        open_vnd,
        high_vnd,
        low_vnd,
        close_vnd,
        lagInFrame(close_vnd) over w as prev_close,
        lagInFrame(trade_date) over w as prev_trade_date,
        lagInFrame(exchange) over w as prev_exchange,
        row_number() over w as rn
    from {{ ref('prices_daily_raw') }}
    window w as (partition by ticker order by trade_date rows between 1 preceding and current row)
),

with_context as (
    select
        b.ticker as ticker,
        b.trade_date as trade_date,
        b.exchange as exchange,
        b.open_vnd as open_vnd,
        b.high_vnd as high_vnd,
        b.low_vnd as low_vnd,
        b.close_vnd as close_vnd,
        b.prev_close as prev_close,
        b.prev_trade_date as prev_trade_date,
        b.prev_exchange as prev_exchange,
        b.rn as rn,
        if(ca.ticker = '', 1.0, ca.adj_ratio) as event_ratio,
        ca.ticker != '' as is_event_day,
        if(s1.exchange = '' or s0.exchange = '', null,
           toNullable(toInt64(s1.session_no) - toInt64(s0.session_no) - 1)) as sessions_missed
    from base as b
    left join {{ ref('int_corporate_actions') }} as ca
        on b.ticker = ca.ticker and b.trade_date = ca.ex_date
    left join {{ ref('int_trading_sessions') }} as s1
        on b.exchange = s1.exchange and b.trade_date = s1.trade_date
    left join {{ ref('int_trading_sessions') }} as s0
        on b.exchange = s0.exchange and b.prev_trade_date = s0.trade_date
),

regimed as (
    select
        *,
        multiIf(
            rn = 1, 'new_listing',
            exchange != prev_exchange, 'exchange_transfer',
            sessions_missed > 25, 'resumption',
            'normal'
        ) as regime,
        {{ reference_method('exchange', 'trade_date') }} as ref_method
    from with_context
),

limited as (
    select
        *,
        if(ref_method = 'prev_close' and rn > 1, toNullable(prev_close / event_ratio), null)
            as ref_price,
        {{ price_limit('exchange', 'regime', 'trade_date') }} as limit_pct,
        {{ price_limit_confidence('exchange', 'regime', 'trade_date') }} as limit_confidence
    from regimed
),

banded as (
    select
        *,
        ref_price * (1 + limit_pct) as ceiling_raw,
        ref_price * (1 - limit_pct) as floor_raw
    from limited
),

ticked as (
    select
        *,
        {{ tick_size('exchange', 'trade_date', 'ref_price') }} as tick_ref,
        {{ tick_size('exchange', 'trade_date', 'ceiling_raw') }} as tick_ceiling,
        {{ tick_size('exchange', 'trade_date', 'floor_raw') }} as tick_floor,
        {{ tick_confidence('exchange', 'trade_date', 'ref_price') }} as tick_confidence
    from banded
),

priced as (
    select
        *,
        -- 1e-9 guards against float noise such as 61800 * 1.07 = 66126.00000000001
        floor(ceiling_raw / tick_ceiling + 1e-9) * tick_ceiling as ceiling_rounded,
        ceil(floor_raw / tick_floor - 1e-9) * tick_floor as floor_rounded
    from ticked
)

select
    ticker,
    trade_date,
    exchange,
    regime,
    ref_method,
    is_event_day,
    event_ratio,
    prev_close,
    ref_price,
    limit_pct,
    if(ceiling_rounded <= ref_price, ref_price + tick_ref, ceiling_rounded) as ceiling_price,
    multiIf(
        floor_rounded >= ref_price and ref_price - tick_ref > 0, ref_price - tick_ref,
        floor_rounded <= 0, ref_price,
        floor_rounded
    ) as floor_price,
    multiIf(
        ref_method != 'prev_close' or rn = 1, 'ref_not_reconstructable',
        limit_pct is null or regime in ('new_listing', 'exchange_transfer'), 'special_regime_unknown',
        'computed'
    ) as limit_status,
    -- Exactly at the limit; a close beyond it is a data problem and shows as outside_band.
    limit_status = 'computed' and abs(close_vnd - ceiling_price) <= 1e-6 as close_at_ceiling,
    limit_status = 'computed' and abs(close_vnd - floor_price) <= 1e-6 as close_at_floor,
    limit_status = 'computed'
        and (greatest(open_vnd, high_vnd, close_vnd) > ceiling_price + 1e-6
             or least(open_vnd, low_vnd, close_vnd) < floor_price - 1e-6) as outside_band,
    -- weakest evidence behind the rules used for this row
    multiIf(
        limit_status != 'computed', '',
        limit_confidence = 'unverified' or tick_confidence = 'unverified', 'unverified',
        limit_confidence = 'verified-secondary' or tick_confidence = 'verified-secondary',
            'verified-secondary',
        'verified-official'
    ) as rule_confidence,
    open_vnd,
    high_vnd,
    low_vnd,
    close_vnd
from priced
