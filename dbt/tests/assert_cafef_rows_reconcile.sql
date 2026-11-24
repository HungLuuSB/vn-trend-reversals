-- Nothing is lost between layers:
--   source rows of the pinned archives = staged rows = checked rows;
--   checked rows (raw, share, kept)    = prices_daily_raw rows;
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
        (select count() from {{ ref('prices_daily_raw') }}) as n_clean,
        (select count() from {{ ref('int_cafef__eod_checked') }}
            where dq_outcome = 'rejected') as n_rejected,
        (select count() from {{ ref('qa_cafef_rejects') }}) as n_quarantine
)

select *
from counts
where n_archives != 2
   or n_source != n_staged
   or n_staged != n_checked
   or n_kept != n_clean
   or n_rejected != n_quarantine
