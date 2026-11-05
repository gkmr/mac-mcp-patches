#!/bin/bash
# Apply, check or revert the unofficial Apple Notes patch on the installed
# "Read and Write Apple Notes" Claude desktop extension (server/index.js, v0.1.7).
# Usage: ./apply-patch.sh [--check] [--revert] [--ext-dir DIR]   (--help for more)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PATCH_ID="notes"
DISPLAY_NAME="Read and Write Apple Notes"
EXPECTED_VERSION="0.1.7"
PATCH_FILE="$HERE/notes-v0.1.7-bulk-list-timeouts.patch"
FINGERPRINT='name: "Apple-Notes-Server"'
MARKER="Patched 2026-07-07"
. "$HERE/../../lib/apply-common.sh"
run_patch "$@"
