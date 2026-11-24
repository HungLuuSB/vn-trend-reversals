{#
  CLAUDE.md data rule 4 / proposal "Leakage controls" 1: a value may enter a feature only if it
  was public before the decision time. Fails on every row where available_at >= decision time.
  Never disable or weaken this test.
#}
{% test no_feature_after_decision_time(model, available_at_column, decision_time_column) %}
select *
from {{ model }}
where {{ available_at_column }} is not null
  and {{ available_at_column }} >= {{ decision_time_column }}
{% endtest %}
