{{ config(order_by='(ticker, status)') }}

-- Final (post-adjudication) events vs Yahoo: shows what adjudication changed.
{{ yahoo_comparison(ref('int_corporate_actions_final')) }}
