# Research snapshots

Every snapshot that models read, frozen by `research/snapshot.py`. The id is derived from the
content (file hashes plus the manifest: git commit, pinned raw archives, seed hashes, SQL and
row counts). The files live in `research/snapshots/<id>/` (not in git) and in the raw layer
under `snapshots/<id>/`.

- **Dev snapshots** are for building and testing code.
- **The final snapshot** for the paper is frozen mid-February 2027 (`docs/proposal.md`,
  timeline). Its id is cited in the paper.

| Snapshot id | Date | Label | Git commit | Rows |
| --- | --- | --- | --- | --- |
