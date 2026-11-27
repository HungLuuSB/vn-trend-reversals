#!/usr/bin/env bash
# Install Wiley's LaTeX authoring template (USG.cls, "Optimal Design" layout) into papers/paper1/.
# The class files are Wiley's copyright ("all rights reserved"), so they are not committed: this
# script extracts them from the zip the authors downloaded (default: the literature inbox).
#   scripts/setup-wiley-template.sh [path/to/WileyDesign.zip]
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
zip=${1:-"$repo/research/literature/inbox/WileyDesign.zip"}
dest="$repo/papers/paper1"
tmp=$(mktemp -d)
trap 'rm -rf -- "${tmp:?}"' EXIT
unzip -q "$zip" -d "$tmp"
src=$(dirname "$(find "$tmp" -name USG.cls | head -1)")
cp "$src/USG.cls" "$src/NJDapacite.sty" "$dest/"
cp "$src/LETTERSP.STY" "$dest/lettersp.sty"   # the class asks for lower case
mkdir -p "$dest/images"
cp "$src/images/ORCID_Logo-eps-converted-to.pdf" "$dest/images/ORCID_Logo.pdf"
# The class's APA option asks for WileyNJD-APA.bst, which the zip lacks; apacite.bst (CTAN, LPPL)
# is the APA style it is built on. Tectonic downloads it on first use of the apacite package.
bst=$(find "$HOME/.cache/tectonic" -name apacite.bst 2>/dev/null | head -1)
if [ -z "$bst" ]; then
  echo "apacite.bst not in the tectonic cache: compile any document that uses apacite once" >&2
  exit 1
fi
cp "$bst" "$dest/WileyNJD-APA.bst"
echo "installed the Wiley template into $dest"
