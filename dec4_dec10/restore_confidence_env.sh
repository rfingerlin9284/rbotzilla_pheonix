#!/usr/bin/env bash
#
# restore_confidence_env.sh – revert Balanced profile to original confidence/env logic
#
# This script compares the current Rbotzilla Phoenix repository with the baseline
# configuration from the main branch and restores the original confidence and
# environment logic while leaving the strategy and stop‑loss logic untouched.
#
# Specifically it performs the following actions:
#
# 1. Resets the charter constants `MIN_EXPECTED_PNL_USD` and `MIN_NOTIONAL_USD`
#    in the three charter files (foundation/rick_charter.py,
#    oanda/foundation/rick_charter.py and rick_hive/rick_charter.py) back to
#    their original values (MIN_EXPECTED_PNL_USD=100.0 and
#    MIN_NOTIONAL_USD=10000) to restore the confidence threshold and notional
#    limit enforced by the baseline profile. Adjust these variables below if
#    your baseline uses different numbers.
#
# 2. Restores the legacy fallback in the OANDA connector so that the
#    expected PnL threshold falls back to 100.0 when the charter constant is
#    missing.  This re‑introduces the environment logic that was removed
#    during the Balanced profile tuning.  Other functionality (strategy sizing,
#    stop‑loss / take‑profit placement, trailing logic etc.) is left intact.
#
# Usage:
#   bash restore_confidence_env.sh
#
# This script is idempotent: running it multiple times will leave the files
# unchanged after the first successful run.

set -euo pipefail

# Baseline values – modify these if your original profile uses different
# constants.  For example, some versions require MIN_NOTIONAL_USD=15000.
MIN_EXPECTED_PNL_USD=100.0
MIN_NOTIONAL_USD=10000

# List of charter files to update
CHARTER_FILES=(
  "foundation/rick_charter.py"
  "oanda/foundation/rick_charter.py"
  "rick_hive/rick_charter.py"
)

echo "Restoring charter constants..."
for file in "${CHARTER_FILES[@]}"; do
  if [[ -f "$file" ]]; then
    # Create a backup if one doesn't already exist for this run
    if [[ ! -f "${file}.bak-restore" ]]; then
      cp -p "$file" "${file}.bak-restore"
    fi
    # Replace MIN_EXPECTED_PNL_USD value
    sed -Ei "s/(MIN_EXPECTED_PNL_USD\s*=\s*)[0-9.]+/\1${MIN_EXPECTED_PNL_USD}/" "$file"
    # Replace MIN_NOTIONAL_USD value
    sed -Ei "s/(MIN_NOTIONAL_USD\s*=\s*)[0-9.]+/\1${MIN_NOTIONAL_USD}/" "$file"
    echo "  Updated $file"
  else
    echo "  Warning: $file not found – skipping"
  fi
done

# Restore the fallback logic in the OANDA connector
OANDA_CONNECTOR="oanda/brokers/oanda_connector.py"
if [[ -f "$OANDA_CONNECTOR" ]]; then
  if [[ ! -f "${OANDA_CONNECTOR}.bak-restore" ]]; then
    cp -p "$OANDA_CONNECTOR" "${OANDA_CONNECTOR}.bak-restore"
  fi
  # Ensure os is imported (needed for getenv fallback)
  if ! grep -q "import os" "$OANDA_CONNECTOR"; then
    sed -i '1iimport os' "$OANDA_CONNECTOR"
  fi
  # Reinstate the fallback: expected PnL uses env var when charter constant is missing
  # Replace the min_expected assignment if it currently references the charter directly.
  # This substitution will work whether the line exists or has been removed; if not
  # found, no change is made.
  sed -Ei \
    "s/min_expected\s*=\s*getattr\(RickCharter,\s*\"MIN_EXPECTED_PNL_USD\",[^)]*\)/min_expected = float(os.getenv(\"MIN_EXPECTED_PNL_USD\", \"${MIN_EXPECTED_PNL_USD}\"))/" \
    "$OANDA_CONNECTOR"
  echo "Restored fallback logic in $OANDA_CONNECTOR"
else
  echo "Warning: $OANDA_CONNECTOR not found – skipping fallback restoration"
fi

echo "Confidence and environment logic restoration complete."