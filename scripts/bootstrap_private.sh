#!/usr/bin/env bash
# Pull the private data files into a fresh crowds checkout.
#
# The curated persona library and the survey microdata are gitignored here
# on purpose, so a clone (cloud session, new machine, CI) starts without
# them and cannot run a real simulation. This copies them in from the
# private companion repo.
#
#   bash scripts/bootstrap_private.sh            # fill in what's missing
#   bash scripts/bootstrap_private.sh --force    # overwrite what's there
#
# Secrets are NOT carried by this script. Set the API keys as environment
# variables (cloud session secrets, Railway variables, or a local .env);
# env.root.template in the private repo lists the names.

set -euo pipefail

PRIVATE_DATA_REPO="${PRIVATE_DATA_REPO:-https://github.com/umovu/crowds-private-data.git}"
PRIVATE_DATA_REF="${PRIVATE_DATA_REF:-main}"

FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Paths are identical on both sides: the private repo mirrors this tree.
PATHS=(
  "backend/app/data/persona_library/personas.json"
  "backend/data/microdata/attitudes/afrobarometer_r9_sa.sav"
  "backend/data/microdata/attitudes/synthetic_donor.json"
  "backend/data/microdata/ghs-2025-v1/ghs-2025-household-v1.dta"
  "backend/data/microdata/ghs-2025-v1/ghs-2025-person-v1.dta"
)

# Nothing to do if every file is already here and we're not forcing.
if [ "$FORCE" -eq 0 ]; then
  missing=0
  for path in "${PATHS[@]}"; do
    [ -f "$REPO_ROOT/$path" ] || missing=1
  done
  if [ "$missing" -eq 0 ]; then
    echo "Private data already in place. Use --force to refresh it."
    exit 0
  fi
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "Cloning $PRIVATE_DATA_REPO ($PRIVATE_DATA_REF)..."
git clone --depth 1 --branch "$PRIVATE_DATA_REF" "$PRIVATE_DATA_REPO" "$TMP_DIR/private" >/dev/null 2>&1 || {
  echo "Could not clone $PRIVATE_DATA_REPO." >&2
  echo "Check that this machine is authenticated for that private repo" >&2
  echo "(gh auth login, or an https token in the URL)." >&2
  exit 1
}

copied=0
skipped=0
for path in "${PATHS[@]}"; do
  src="$TMP_DIR/private/$path"
  dest="$REPO_ROOT/$path"
  if [ ! -f "$src" ]; then
    echo "  missing in private repo: $path" >&2
    continue
  fi
  if [ -f "$dest" ] && [ "$FORCE" -eq 0 ]; then
    skipped=$((skipped + 1))
    continue
  fi
  mkdir -p "$(dirname "$dest")"
  cp "$src" "$dest"
  copied=$((copied + 1))
  echo "  $path"
done

echo "Copied $copied file(s), left $skipped in place."
echo
echo "Remaining step: export the API keys listed in the private repo's"
echo "env.root.template (LLM_API_KEY, SIM_LLM_API_KEY, SECRET_KEY, ...)."
