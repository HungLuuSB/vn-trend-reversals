"""Download CafeF archives and store them, unchanged, in the raw layer.

Usage (from the repo root, with the research stack running):

    uv run python -m vnbank.ingestion.market.cafef_ingest                 # latest raw + adjusted
    uv run python -m vnbank.ingestion.market.cafef_ingest --date 2026-11-20 --variant raw

Re-running is safe: identical bytes map to the same key and are not stored twice.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from vnbank.common.env import load_dotenv
from vnbank.common.raw_store import RawObject, RawStore, S3RawStore, raw_key, sha256_hex
from vnbank.ingestion.market.cafef_client import USER_AGENT, CafefArchive, CafefClient, Variant

SOURCE = "cafef"


def store_archive(store: RawStore, archive: CafefArchive) -> RawObject:
    digest = sha256_hex(archive.content)
    key = raw_key(SOURCE, archive.fetched_at_utc, archive.filename, digest)
    metadata = {
        "source": SOURCE,
        "source_url": archive.url,
        "variant": str(archive.variant),
        "upto_date": archive.as_of.isoformat(),
        "fetched_at_utc": archive.fetched_at_utc.isoformat(),
        "http_last_modified": archive.last_modified or "",
        "client": USER_AGENT,
    }
    return store.put_immutable(key, archive.content, metadata)


def ingest(
    client: CafefClient,
    store: RawStore,
    variants: list[Variant],
    as_of: date | None = None,
) -> list[RawObject]:
    stored = []
    for variant in variants:
        if as_of is None:
            archive = client.fetch_latest(variant)
        else:
            archive = client.fetch(as_of, variant)
            if archive is None:
                raise LookupError(f"CafeF has no {variant} archive for {as_of}")
        stored.append(store_archive(store, archive))
    return stored


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--date", type=date.fromisoformat, help="archive 'Upto' date (default: latest)"
    )
    parser.add_argument("--variant", choices=["raw", "adjusted", "both"], default="both")
    args = parser.parse_args(argv)

    variants = (
        [Variant.RAW, Variant.ADJUSTED] if args.variant == "both" else [Variant(args.variant)]
    )
    load_dotenv(["S3_"])
    results = ingest(CafefClient(), S3RawStore.from_env(), variants, args.date)
    for obj in results:
        print(
            json.dumps(
                {"key": obj.key, "size": obj.size, "sha256": obj.sha256, "created": obj.created}
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
