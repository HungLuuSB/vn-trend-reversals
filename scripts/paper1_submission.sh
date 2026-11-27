#!/usr/bin/env bash
# Build the Journal of Forecasting submission bundle for Paper 1 (Wiley free-format, LaTeX route).
#   scripts/paper1_submission.sh            -> data/submission/paper1-<date>/ and a .zip of it
# Upload (Research Exchange): main.tex as "Main Document - LaTeX .tex File", main.pdf as
# "Main Document - LaTeX PDF", every other file of latex/ (one flat folder) as "LaTeX Supplementary File", and
# supplement.pdf as Supporting Information. The cover letter goes in its own field.
# Requires the Wiley template (scripts/setup-wiley-template.sh) and committed sources.
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
src="$repo/papers/paper1"
if [ -n "$(git -C "$repo" status --porcelain --untracked-files=no -- papers/paper1)" ]; then
  echo "papers/paper1 has uncommitted changes: commit them first" >&2
  exit 1
fi
out="$repo/data/submission/paper1-$(date +%Y%m%d)"
rm -rf -- "${out:?}"
mkdir -p "$out/latex"
build=$(mktemp -d)
trap 'rm -rf -- "${build:?}"' EXIT

# compile in a copy of the sources, in this order: main (writes main.aux), supplement (reads it
# for references to the main text), main again (reads supplement.aux for references to Appendix
# S1; package xr). Keeps the .bbl so the editorial system needs no BibTeX run.
cp -r "$src/." "$build/"
for doc in main supplement main; do
  (cd "$build" && tectonic -X compile --keep-intermediates --keep-logs "$doc.tex" >/dev/null)
done
if grep -qE "Reference .* undefined|Citation .* undefined" "$build/main.log" "$build/supplement.log"; then
  echo "undefined references:" >&2
  grep -hE "Reference .* undefined|Citation .* undefined" "$build/main.log" "$build/supplement.log" >&2
  exit 1
fi

cp "$src/main.tex" "$src/refs.bib" "$build/main.bbl" "$build/supplement.aux" "$out/latex/"
cp "$src/USG.cls" "$src/NJDapacite.sty" "$src/lettersp.sty" "$src/WileyNJD-APA.bst" "$out/latex/"
# flat: every file in one folder (submission systems may drop subfolders); the copies'
# paths to sections/, generated/ and images/ are rewritten to match
cp "$src"/sections/0*.tex "$src"/generated/*.tex "$src"/images/ORCID_Logo.pdf "$out/latex/"
sed -i -E 's#(sections|generated|images)/##g' "$out"/latex/*.tex "$out/latex/USG.cls"
if [ "$(find "$out/latex" -type f | sed 's#.*/##' | sort | uniq -d)" ]; then
  echo "file name clash in the flat bundle" >&2; exit 1
fi
cp "$build/main.pdf" "$out/main.pdf"
cp "$build/supplement.pdf" "$out/supplement.pdf"
cp "$src/cover_letter.md" "$out/cover_letter.md"

# the bundle must compile on its own
check=$(mktemp -d)
cp -r "$out/latex/." "$check/"
(cd "$check" && tectonic -X compile --keep-logs main.tex >/dev/null) || { echo "bundle does not compile" >&2; exit 1; }
if grep -qE "Reference .* undefined" "$check/main.log"; then echo "bundle has undefined references" >&2; exit 1; fi
rm -rf -- "${check:?}"

git -C "$repo" rev-parse --short HEAD > "$out/COMMIT"
python3 -c "import shutil,sys; shutil.make_archive(sys.argv[1], 'zip', sys.argv[2], sys.argv[3])" \
  "$out" "$(dirname "$out")" "$(basename "$out")"
echo "submission bundle: $out (and $out.zip)"
