-- One row per line of the pinned CafeF archives (vars.cafef_archives), typed and labelled.
-- Nothing is removed here: quality decisions happen in int_cafef__eod_checked.
{% set archives = var('cafef_archives') %}

select
    -- Only two distinct values per column: dictionary-encode so wide rows stay cheap to sort.
    toLowCardinality(raw_key) as raw_key,
    toLowCardinality(raw_sha256) as raw_sha256,
    variant,
    upto,
    source_file,
    row_num,
    exchange,
    ticker,
    trade_date,

    -- Label by ticker pattern (a documented heuristic, ADR 0002). Order matters:
    -- index names like VNXALL would otherwise not match, and 3-character VNX is a real share.
    multiIf(
        ticker = '' or ticker = '0', 'invalid',
        ticker in ('VNXALL', 'VNX-ALL') or position(ticker, 'INDEX') > 0, 'index',
        match(ticker, '^C[A-Z0-9]{3}[0-9]{4}$'), 'warrant',
        match(ticker, '^(E1VFVN3[0-9]|FU[A-Z0-9]{6})$'), 'fund',
        match(ticker, '^[A-Z][A-Z0-9]{2}$'), 'share',
        'other'
    ) as instrument_type,

    -- CafeF publishes thousand VND; convert to VND. round() removes float noise (61.8 * 1000).
    round(open * 1000, 4) as open_vnd,
    round(high * 1000, 4) as high_vnd,
    round(low * 1000, 4) as low_vnd,
    round(close * 1000, 4) as close_vnd,
    volume,

    -- When the day's prices became public: the session close, 15:00 Asia/Ho_Chi_Minh (CLAUDE.md
    -- data rule 3). Features may use a row only if available_at_utc < the 09:00 decision time.
    toTimeZone(
        toDateTime64(concat(toString(trade_date), ' 15:00:00'), 3, 'Asia/Ho_Chi_Minh'), 'UTC'
    ) as available_at_utc,

    toLowCardinality(load_run_id) as load_run_id
from {{ source('cafef', 'raw_cafef_eod') }}
where raw_key in ('{{ archives["raw"] }}', '{{ archives["adjusted"] }}')
