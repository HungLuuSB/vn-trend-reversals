# ADR 0001: SeaweedFS instead of MinIO for the raw layer

- **Status:** accepted
- **Date:** 2026-11-24

## Context

The plan uses MinIO as the immutable raw layer (`raw/<source>/<yyyy-mm-dd>/…`). In November 2026, `minio/minio` no longer exists on Docker Hub, and `quay.io/minio/minio` and `ghcr.io/minio/minio` refuse anonymous pulls. MinIO stopped distributing community binaries and images in late 2025.

The raw layer only needs the S3 API: put/get objects, list by prefix, and versioning or write-once behaviour. Our code talks to it through boto3, so any S3-compatible store works.

## Options considered

| Option | For | Against |
| --- | --- | --- |
| SeaweedFS | Mature (10+ years), Apache-2.0, one container (`weed server -s3`), light on RAM, versioned images | No MinIO-style web console |
| RustFS | Built as a MinIO drop-in, has a console | Young project (1.0 in late 2026) |
| Build MinIO from source | Keeps the original plan's name | We would maintain our own image |
| Local filesystem | Simplest | No S3 API; less useful for the portfolio |

## Decision

Use **SeaweedFS** (`chrislusf/seaweedfs:4.52`, the newest release at least two weeks old on 2026-11-24) as a single-node S3 gateway in the `research` profile. Ingestion code uses only the S3 API through our own wrapper, so the store can be swapped later.

## Consequences

- Env vars are `S3_*` rather than `MINIO_*`; the S3 endpoint is `http://localhost:8333`.
- "MinIO" in the project summary and CLAUDE.md now means "the S3 raw layer (SeaweedFS)".
- Immutability is enforced in our raw-writer code (refuse to overwrite an existing key) rather than relying on store features.
