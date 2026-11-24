{{ config(order_by='(ticker, status)') }}

-- Inferred (pre-adjudication) events vs Yahoo. Defines the D-007 dispute queue.
{{ yahoo_comparison(ref('int_corporate_actions')) }}
