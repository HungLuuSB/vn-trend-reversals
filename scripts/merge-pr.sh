#!/usr/bin/env bash
# Merge a PR only after its CI check has registered AND passed (stops on failure).
# Usage: scripts/merge-pr.sh <pr-number>
set -euo pipefail
pr="$1"
for _ in $(seq 1 60); do
  gh pr checks "$pr" 2>/dev/null | grep -q "lint-and-test" && break
  sleep 5
done
gh pr checks "$pr" | grep -q "lint-and-test" || { echo "no CI check registered for #$pr" >&2; exit 1; }
gh pr checks "$pr" --watch --fail-fast --interval 10   # non-zero exit if the check fails
gh pr checks "$pr" | grep "lint-and-test" | grep -q "pass" || { echo "CI did not pass for #$pr" >&2; exit 1; }
gh pr merge "$pr" --merge
