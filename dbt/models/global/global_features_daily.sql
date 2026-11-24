-- depends_on: {{ ref('global_series') }}
{{ config(materialized='table', order_by='(trade_date)') }}

-- Feature block D (docs/proposals/paper1-trend-reversals.md; research/DECISIONS.md D-009): one row per HOSE session.
-- Each change is measured between the values public at this session's 09:00 decision time and
-- at the previous HOSE session's, so across Vietnamese holidays (e.g. Tet) it is the
-- cumulative change since the last Vietnamese session (CLAUDE.md rule 8).
--   price series (indices, FX, futures): log return
--   level series (VIX, US 10-year yield, GPR): difference; GPR levels are kept as well
-- available_at_max_utc is the latest availability time among the inputs of the row; the
-- no_feature_after_decision_time test checks it against decision_time_utc.

{% set price_series = ['spx', 'nasdaq', 'dxy', 'gold', 'brent', 'hsi', 'sse', 'usdvnd', 'usdcny'] %}
{% set level_series = ['vix', 'ust10', 'gpr', 'gpr_act', 'gpr_threat'] %}

with changes as (
    select
        trade_date,
        decision_time_utc,
        series_id,
        value,
        available_at_utc,
        staleness_days,
        lagInFrame(value) over w as prev_value,
        lagInFrame(available_at_utc) over w as prev_available_at_utc
    from {{ ref('global_asof_daily') }}
    window w as (partition by series_id order by trade_date rows between 1 preceding and current row)
)

select
    trade_date,
    any(decision_time_utc) as decision_time_utc,
    {%- for s in price_series %}
    anyIf(if(prev_value > 0 and value > 0, log(value / prev_value), null), series_id = '{{ s }}')
        as {{ s }}_ret,
    {%- endfor %}
    {%- for s in level_series %}
    anyIf(value - prev_value, series_id = '{{ s }}') as {{ s }}_chg,
    {%- endfor %}
    anyIf(value, series_id = 'vix') as vix_level,
    anyIf(value, series_id = 'ust10') as ust10_level,
    anyIf(value, series_id = 'gpr') as gpr_level,
    anyIf(value, series_id = 'gpr_act') as gpr_act_level,
    anyIf(value, series_id = 'gpr_threat') as gpr_threat_level,
    max(staleness_days) as max_staleness_days,
    -- Front-month COMEX gold rolls late in Jan, Mar, May, Jul, Sep and Nov; returns in these
    -- windows can contain a roll jump (D-009). Flagged here; treatment set with the features.
    toMonth(trade_date) in (1, 3, 5, 7, 9, 11) and toDayOfMonth(trade_date) >= 22
        as gold_roll_window,
    max(available_at_utc) as available_at_max_utc
from changes
group by trade_date
