#!/usr/bin/env bash
# Build the Journal of Forecasting submission bundle for Paper 1 (Wiley free-format, LaTeX route).
#   scripts/paper1_submission.sh            -> data/submission/paper1-<date>/ and a .zip of it
# Upload (Research Exchange): main.tex as "Main Document - LaTeX .tex File", main.pdf as
# "Main Document - LaTeX PDF", every other file of latex/ as "LaTeX Supplementary File", and
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

# compile once, keeping the .bbl so the editorial system needs no BibTeX run
(cd "$src" && tectonic -X compile --keep-intermediates --outdir "$build" main.tex >/dev/null)
(cd "$src" && tectonic -X compile --outdir "$build" supplement.tex >/dev/null)

cp "$src/main.tex" "$src/refs.bib" "$build/main.bbl" "$out/latex/"
cp "$src/USG.cls" "$src/NJDapacite.sty" "$src/lettersp.sty" "$src/WileyNJD-APA.bst" "$out/latex/"
mkdir -p "$out/latex/sections" "$out/latex/generated" "$out/latex/images"
cp "$src"/sections/0*.tex "$out/latex/sections/"
cp "$src"/generated/*.tex "$out/latex/generated/"
cp "$src"/images/ORCID_Logo.pdf "$out/latex/images/"
cp "$build/main.pdf" "$out/main.pdf"
cp "$build/supplement.pdf" "$out/supplement.pdf"
cp "$src/cover_letter.md" "$out/cover_letter.md"

# the bundle must compile on its own
check=$(mktemp -d)
cp -r "$out/latex/." "$check/"
(cd "$check" && tectonic -X compile main.tex >/dev/null) || { echo "bundle does not compile" >&2; exit 1; }
rm -rf -- "${check:?}"

git -C "$repo" rev-parse --short HEAD > "$out/COMMIT"
python3 -c "import shutil,sys; shutil.make_archive(sys.argv[1], 'zip', sys.argv[2], sys.argv[3])" \
  "$out" "$(dirname "$out")" "$(basename "$out")"
echo "submission bundle: $out (and $out.zip)"
