{#
  Adjustment ratio of a corporate action from verified facts (research/DECISIONS.md D-007):
      reference = (P - cash + rights_ratio * rights_price) / (1 + stock_ratio + rights_ratio)
      ratio     = P / reference
  P is the raw close on the last trading day before the ex-date. A rights issue priced at or
  above P has no economic value to existing holders and is ignored (the exchange does not adjust
  the reference for it either; D-003).
#}
{% macro corporate_action_ratio(p, cash, stock_ratio, rights_ratio, rights_price) %}
    ({{ p }} / (
        ({{ p }} - {{ cash }}
            + if({{ rights_price }} < {{ p }}, {{ rights_ratio }} * {{ rights_price }}, 0))
        / (1 + {{ stock_ratio }} + if({{ rights_price }} < {{ p }}, {{ rights_ratio }}, 0))
    ))
{% endmacro %}
