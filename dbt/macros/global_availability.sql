{#
  available_at_utc for a global observation, from seed global_series (research/paper1/DECISIONS.md D-009).
  ClickHouse needs a constant time zone per toDateTime64 call, so one branch is generated per
  series from the seed at build time.
    close             : obs_date + close_time_local in close_tz
    next_day_midnight : (obs_date + 1 day) 00:00 in close_tz
    gpr_weekly        : 00:00 close_tz on the Wednesday after the first Monday strictly after
                        obs_date (GPR is updated on Mondays, holidays the next business day)
#}
{% macro global_available_at(series_col, date_col) %}
    {%- set rows = [] -%}
    {%- if execute -%}
        {%- set res = run_query("select series_id, availability_rule, close_time_local, close_tz from " ~ target.schema ~ ".global_series order by series_id") -%}
        {%- set rows = res.rows -%}
    {%- endif -%}
    multiIf(
    {%- for r in rows %}
        {%- if r[1] == 'close' %}
        {{ series_col }} = '{{ r[0] }}',
            toTimeZone(toDateTime64(concat(toString({{ date_col }}), ' {{ r[2] }}'), 3, '{{ r[3] }}'), 'UTC'),
        {%- elif r[1] == 'next_day_midnight' %}
        {{ series_col }} = '{{ r[0] }}',
            toTimeZone(toDateTime64(concat(toString({{ date_col }} + 1), ' 00:00:00'), 3, '{{ r[3] }}'), 'UTC'),
        {%- elif r[1] == 'gpr_weekly' %}
        {{ series_col }} = '{{ r[0] }}',
            toTimeZone(toDateTime64(concat(toString(toMonday({{ date_col }}) + 7 + 2), ' 00:00:00'), 3, '{{ r[3] }}'), 'UTC'),
        {%- endif %}
    {%- endfor %}
        toDateTime64('2299-12-31 00:00:00', 3, 'UTC'))
{% endmacro %}
