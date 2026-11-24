"""Immutable raw layer (CLAUDE.md data rule 1).

Every download is written here, unchanged, before anything parses it. Keys look like
``<source>/<yyyy-mm-dd>/<stem>.<sha8><suffix>`` inside the ``raw`` bucket, where the date is the
UTC download date and ``sha8`` is the first 8 hex digits of the content's SHA-256. Including the
hash means a changed file never overwrites an earlier one: it gets a new key.

Writes are idempotent: storing identical bytes under an existing key is a no-op; different bytes
under an existing key raise ``RawObjectConflictError``. Nothing in this module deletes objects.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


class RawObjectConflictError(RuntimeError):
    """A different object already exists under the key; raw objects are never overwritten."""


@dataclass(frozen=True)
class RawObject:
    key: str
    sha256: str
    size: int
    metadata: Mapping[str, str] = field(default_factory=dict)
    created: bool = True  # False when an identical object was already stored


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def raw_key(source: str, fetched_at_utc: datetime, filename: str, sha256: str) -> str:
    """Build ``<source>/<yyyy-mm-dd>/<stem>.<sha8><suffix>`` from the UTC download time."""
    if fetched_at_utc.tzinfo is None:
        raise ValueError("fetched_at_utc must be timezone-aware")
    if not source or "/" in source:
        raise ValueError(f"invalid source name: {source!r}")
    name = PurePosixPath(filename).name
    if not name or name != filename:
        raise ValueError(f"filename must be a bare file name: {filename!r}")
    day = fetched_at_utc.astimezone(UTC).date().isoformat()
    suffix = _extension(name)
    stem = name[: len(name) - len(suffix)] if suffix else name
    return f"{source}/{day}/{stem}.{sha256[:8]}{suffix}"


_COMPRESSION = {".gz", ".bz2", ".xz", ".zst"}


def _extension(name: str) -> str:
    """Last suffix, or the last two for compressed files (``.csv.gz``).

    File names like ``CafeF.SolieuGD.Raw.Upto20112026.zip`` contain dots that are not extensions,
    so ``PurePosixPath.suffixes`` cannot be used as is.
    """
    suffixes = PurePosixPath(name).suffixes
    if len(suffixes) >= 2 and suffixes[-1] in _COMPRESSION:
        return "".join(suffixes[-2:])
    return suffixes[-1] if suffixes else ""


class RawStore(Protocol):
    def put_immutable(
        self, key: str, data: bytes, metadata: Mapping[str, str] | None = None
    ) -> RawObject: ...

    def get(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...


class InMemoryRawStore:
    """Raw store for tests; same semantics as ``S3RawStore``."""

    def __init__(self) -> None:
        self._objects: dict[str, tuple[bytes, dict[str, str]]] = {}

    def put_immutable(
        self, key: str, data: bytes, metadata: Mapping[str, str] | None = None
    ) -> RawObject:
        digest = sha256_hex(data)
        meta = {**(metadata or {}), "sha256": digest}
        if key in self._objects:
            existing, existing_meta = self._objects[key]
            if sha256_hex(existing) != digest:
                raise RawObjectConflictError(f"different content already stored at {key}")
            return RawObject(key, digest, len(existing), existing_meta, created=False)
        self._objects[key] = (bytes(data), meta)
        return RawObject(key, digest, len(data), meta, created=True)

    def get(self, key: str) -> bytes:
        return self._objects[key][0]

    def exists(self, key: str) -> bool:
        return key in self._objects

    def keys(self) -> list[str]:
        return sorted(self._objects)


class S3RawStore:
    """Raw store on any S3-compatible service (SeaweedFS locally; see ADR 0001)."""

    def __init__(self, client, bucket: str) -> None:
        self._s3 = client
        self.bucket = bucket

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> S3RawStore:
        """Build from ``S3_ENDPOINT``, ``S3_ACCESS_KEY``, ``S3_SECRET_KEY``, ``S3_RAW_BUCKET``."""
        env = os.environ if env is None else env
        missing = [k for k in ("S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY") if not env.get(k)]
        if missing:
            raise RuntimeError(f"missing environment variables: {', '.join(missing)}")
        client = boto3.client(
            "s3",
            endpoint_url=env["S3_ENDPOINT"],
            aws_access_key_id=env["S3_ACCESS_KEY"],
            aws_secret_access_key=env["S3_SECRET_KEY"],
            region_name="us-east-1",
            config=Config(
                s3={"addressing_style": "path"},
                retries={"max_attempts": 5, "mode": "standard"},
                # Checksums only when an operation requires them; SeaweedFS rejects some
                # of the newer default trailing-checksum headers.
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )
        store = cls(client, env.get("S3_RAW_BUCKET") or "raw")
        store.ensure_bucket()
        return store

    def ensure_bucket(self) -> None:
        try:
            self._s3.head_bucket(Bucket=self.bucket)
        except ClientError as e:
            if _status(e) != 404:
                raise
            self._s3.create_bucket(Bucket=self.bucket)

    def _head(self, key: str) -> dict | None:
        try:
            return self._s3.head_object(Bucket=self.bucket, Key=key)
        except ClientError as e:
            if _status(e) == 404:
                return None
            raise

    def exists(self, key: str) -> bool:
        return self._head(key) is not None

    def put_immutable(
        self, key: str, data: bytes, metadata: Mapping[str, str] | None = None
    ) -> RawObject:
        digest = sha256_hex(data)
        meta = {**(metadata or {}), "sha256": digest}
        _check_metadata(meta)
        head = self._head(key)
        if head is not None:
            existing = head.get("Metadata", {}).get("sha256")
            if existing != digest:
                raise RawObjectConflictError(f"different content already stored at {key}")
            return RawObject(key, digest, int(head["ContentLength"]), head["Metadata"], False)
        self._s3.put_object(Bucket=self.bucket, Key=key, Body=data, Metadata=meta)
        # Read back the stored size so a truncated upload is caught here, not at parse time.
        stored = self._head(key)
        if stored is None or int(stored["ContentLength"]) != len(data):
            raise RuntimeError(f"upload verification failed for {key}")
        return RawObject(key, digest, len(data), meta, created=True)

    def get(self, key: str) -> bytes:
        body = self._s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        return body

    def list_keys(self, prefix: str = "") -> list[str]:
        keys: list[str] = []
        for page in self._s3.get_paginator("list_objects_v2").paginate(
            Bucket=self.bucket, Prefix=prefix
        ):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return sorted(keys)


def _status(e: ClientError) -> int:
    return int(e.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))


def _check_metadata(meta: Mapping[str, str]) -> None:
    # S3 user metadata travels as HTTP headers: ASCII only.
    for k, v in meta.items():
        if not (k.isascii() and str(v).isascii()):
            raise ValueError(f"S3 metadata must be ASCII: {k}={v!r}")
