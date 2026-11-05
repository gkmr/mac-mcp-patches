#!/bin/bash
# Apply, check or revert the unofficial iMessage patch on the installed
# "Read and Send iMessages" Claude desktop extension (server/index.js, v0.1.11).
# Usage: ./apply-patch.sh [--check] [--revert] [--ext-dir DIR]   (--help for more)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PATCH_ID="imessage"
DISPLAY_NAME="Read and Send iMessages"
EXPECTED_VERSION="0.1.11"
PATCH_FILE="$HERE/imessage-v0.1.11-fast-search-sms-fallback.patch"
FINGERPRINT='name: "iMessage-AppleScript-Server"'
MARKER="searchContactsSQLite"
. "$HERE/../../lib/apply-common.sh"
run_patch "$@"
