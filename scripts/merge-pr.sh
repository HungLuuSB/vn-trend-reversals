#!/usr/bin/env bash
# Merge a PR only after its CI check has registered AND passed (stops on failure).
# Usage: scripts/merge-pr.sh <pr-number>
# Note: `gh pr checks` exits non-zero while checks are pending or failed, so its output is
# captured first and inspected separately.
set -euo pipefail
pr="$1"
status() { gh pr checks "$pr" 2>/dev/null || true; }
for _ in $(seq 1 60); do
  grep -q "lint-and-test" <<<"$(status)" && break
  sleep 5
done
grep -q "lint-and-test" <<<"$(status)" || { echo "no CI check registered for #$pr" >&2; exit 1; }
gh pr checks "$pr" --watch --interval 10 >/dev/null 2>&1 || true
line=$(grep "lint-and-test" <<<"$(status)")
echo "$line"
awk -F'\t' '{print $2}' <<<"$line" | grep -qx "pass" || { echo "CI did not pass for #$pr" >&2; exit 1; }
gh pr merge "$pr" --merge
