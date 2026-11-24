{#
  Dated rule schedules (seeds) turned into inline multiIf() expressions at build time.
  The seeds are tiny, so this avoids range joins against millions of price rows.
  Models using these macros must declare the seeds with "-- depends_on: {{ ref('...') }}".
#}

{% macro _seed_rows(seed_name, columns) %}
    {% if execute %}
        {#- Read the seed table directly (not via ref) so unit tests also use the real dated rules;
            models still declare "-- depends_on: ref(seed)" so seeds build first. -#}
        {% set relation = target.schema ~ "." ~ seed_name %}
        {% set result = run_query("select " ~ columns ~ " from " ~ relation ~ " order by valid_from") %}
        {{ return(result.rows) }}
    {% else %}
        {{ return([]) }}
    {% endif %}
{% endmacro %}

{# Tick size (VND) for a price on an exchange and date; nan when no rule covers it. #}
{% macro tick_size(exchange, day, price) %}
    {%- set rows = _seed_rows('tick_size_schedule', 'exchange, valid_from, valid_to, price_from, price_to, tick_vnd') -%}
    multiIf(
    {%- for r in rows %}
        {{ exchange }} = '{{ r[0] }}' and {{ day }} between toDate('{{ r[1] }}') and toDate('{{ r[2] }}')
            and {{ price }} >= {{ r[3] }} and {{ price }} < {{ r[4] }}, toFloat64({{ r[5] }}),
    {%- endfor %}
        nan)
{% endmacro %}

{# Confidence of the tick rule applied ('' when none applies). #}
{% macro tick_confidence(exchange, day, price) %}
    {%- set rows = _seed_rows('tick_size_schedule', 'exchange, valid_from, valid_to, price_from, price_to, confidence') -%}
    multiIf(
    {%- for r in rows %}
        {{ exchange }} = '{{ r[0] }}' and {{ day }} between toDate('{{ r[1] }}') and toDate('{{ r[2] }}')
            and {{ price }} >= {{ r[3] }} and {{ price }} < {{ r[4] }}, '{{ r[5] }}',
    {%- endfor %}
        '')
{% endmacro %}

{# Daily limit (fraction) for an exchange, regime and date; NULL when no rule is known. #}
{% macro price_limit(exchange, regime, day) %}
    {%- set rows = _seed_rows('price_limit_schedule', 'exchange, regime, valid_from, valid_to, limit_pct') -%}
    multiIf(
    {%- for r in rows %}
        {{ exchange }} = '{{ r[0] }}' and {{ regime }} = '{{ r[1] }}'
            and {{ day }} between toDate('{{ r[2] }}') and toDate('{{ r[3] }}'), toNullable(toFloat64({{ r[4] }})),
    {%- endfor %}
        null)
{% endmacro %}

{% macro price_limit_confidence(exchange, regime, day) %}
    {%- set rows = _seed_rows('price_limit_schedule', 'exchange, regime, valid_from, valid_to, confidence') -%}
    multiIf(
    {%- for r in rows %}
        {{ exchange }} = '{{ r[0] }}' and {{ regime }} = '{{ r[1] }}'
            and {{ day }} between toDate('{{ r[2] }}') and toDate('{{ r[3] }}'), '{{ r[4] }}',
    {%- endfor %}
        '')
{% endmacro %}

{# How the exchange set the reference price on a date (prev_close, vwap_session, ...). #}
{% macro reference_method(exchange, day) %}
    {%- set rows = _seed_rows('reference_price_rule', 'exchange, valid_from, valid_to, method') -%}
    multiIf(
    {%- for r in rows %}
        {{ exchange }} = '{{ r[0] }}' and {{ day }} between toDate('{{ r[1] }}') and toDate('{{ r[2] }}'), '{{ r[3] }}',
    {%- endfor %}
        'unknown')
{% endmacro %}
