-- Nothing is lost between layers:
--   source rows of the pinned archives = staged rows = checked rows;
--   checked rows (raw, share, kept)    = bulk rows in prices_daily_raw + bulk rows replaced by fills;
--   kept gap fills                     = cafef_ticker rows in prices_daily_raw;
--   checked rows (rejected)            = qa_cafef_rejects rows;
--   each pinned archive is present in the source.
{% set archives = var('cafef_archives') %}

with counts as (
    select
        (select count() from {{ source('cafef', 'raw_cafef_eod') }}
            where raw_key in ('{{ archives["raw"] }}', '{{ archives["adjusted"] }}')) as n_source,
        (select uniqExact(raw_key) from {{ source('cafef', 'raw_cafef_eod') }}
            where raw_key in ('{{ archives["raw"] }}', '{{ archives["adjusted"] }}')) as n_archives,
        (select count() from {{ ref('stg_cafef__eod') }}) as n_staged,
        (select count() from {{ ref('int_cafef__eod_checked') }}) as n_checked,
        (select count() from {{ ref('int_cafef__eod_checked') }}
            where variant = 'raw' and instrument_type = 'share' and dq_outcome = 'kept') as n_kept,
        (select countIf(price_source = 'cafef_bulk') from {{ ref('prices_daily_raw') }})
            as n_clean_bulk,
        (select countIf(price_source = 'cafef_ticker') from {{ ref('prices_daily_raw') }})
            as n_clean_fill,
        (select count() from {{ ref('int_price_gap_fills') }} where dq_outcome = 'kept')
            as n_fills_kept,
        -- bulk rows replaced by a per-ticker fill for the same stock-day
        (select count() from {{ ref('int_cafef__eod_checked') }}
            where variant = 'raw' and instrument_type = 'share' and dq_outcome = 'kept'
              and (ticker, trade_date) in (
                  select ticker, trade_date from {{ ref('int_price_gap_fills') }}
                  where dq_outcome = 'kept'
              )) as n_bulk_replaced,
        (select count() from {{ ref('int_cafef__eod_checked') }}
            where dq_outcome = 'rejected') as n_rejected,
        (select count() from {{ ref('qa_cafef_rejects') }}) as n_quarantine
)

select *
from counts
where n_archives != 2
   or n_source != n_staged
   or n_staged != n_checked
   or n_kept != n_clean_bulk + n_bulk_replaced
   or n_clean_fill != n_fills_kept
   or n_rejected != n_quarantine
