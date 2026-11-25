# Research snapshots

Every snapshot that models read, frozen by `src/vnbank/research/shared/snapshot.py`. The id is derived from the
content (file hashes plus the manifest: git commit, pinned raw archives, seed hashes, SQL and
row counts). The files live in `data/snapshots/<id>/` (not in git) and in the raw layer
under `snapshots/<id>/`.

- **Dev snapshots** are for building and testing code.
- **The final snapshot** for the paper is frozen as soon as the pipeline is complete, target early December 2026 (D-024 / P2-017; originally mid-February 2027 in the
  `docs/proposals/paper1-trend-reversals.md` timeline). Its id is cited in the paper.

| Snapshot id | Date | Label | Git commit | Rows |
| --- | --- | --- | --- | --- |
| `b536ec69488162e0` | 2026-11-24 | dev-v1 | `cf458cb7c4` | universe_daily 146,555, prices_raw 257,233, prices_adjusted 257,233, price_limits 257,233, corporate_actions 1,356, sessions_hose 3,771, vn30_membership 91, bank_spells 39, global_features 3,771, local_market 3,771 |
