#!/bin/bash
# Shared logic for patches/*/apply-patch.sh. Source it, do not run it.
# Written for the bash 3.2 that ships with macOS and for both BSD and GNU patch.
#
# The caller sets:
#   PATCH_ID          short id, names the backup folder (imessage, notes)
#   DISPLAY_NAME      extension name for messages
#   EXPECTED_VERSION  manifest version the patch was built against
#   PATCH_FILE        absolute path of the .patch file
#   FINGERPRINT       text in upstream server/index.js that the patch leaves alone
#   MARKER            text that only the patched file contains
# then calls: run_patch "$@"

usage() {
  cat <<USAGE
Usage: $(basename "$0") [--check] [--revert] [--ext-dir DIR]

Applies the unofficial $DISPLAY_NAME patch (built for v$EXPECTED_VERSION) to the
installed Claude desktop extension. Safe to run more than once.

  --check        say what would happen, change nothing
  --revert       undo the patch (only when it reverses cleanly)
  --ext-dir DIR  use this extension folder instead of searching for it

Environment:
  CLAUDE_EXTENSIONS_DIR       folder to search (default: ~/Library/Application Support/Claude/Claude Extensions)
  MAC_MCP_PATCHES_BACKUP_DIR  backup folder (default: ~/.mac-mcp-patches/backups)

Exit codes: 0 done or nothing to do, 1 refused or failed, 2 usage error or extension not found.
USAGE
}

fail() {
  local code="$1"; shift
  echo "error: $*" >&2
  exit "$code"
}

extensions_root() {
  echo "${CLAUDE_EXTENSIONS_DIR:-$HOME/Library/Application Support/Claude/Claude Extensions}"
}

# Print the one extension folder whose server/index.js contains FINGERPRINT.
find_extension() {
  local root d found="" n=0
  root="$(extensions_root)"
  [ -d "$root" ] || fail 2 "extensions folder not found: $root (set CLAUDE_EXTENSIONS_DIR or pass --ext-dir)"
  for d in "$root"/*/; do
    d="${d%/}"
    [ -f "$d/server/index.js" ] || continue
    if grep -qF "$FINGERPRINT" "$d/server/index.js"; then
      n=$((n + 1))
      found="$found$d
"
    fi
  done
  if [ "$n" -eq 0 ]; then
    fail 2 "no $DISPLAY_NAME extension found under $root (pass --ext-dir)"
  fi
  if [ "$n" -gt 1 ]; then
    echo "more than one $DISPLAY_NAME extension found:" >&2
    printf '%s' "$found" | sed 's/^/  /' >&2
    fail 2 "pass --ext-dir to pick one"
  fi
  printf '%s' "$found" | head -1
}

# Top-level "version" from manifest.json: plutil on macOS, then python3, then sed.
read_version() {
  local m="$1/manifest.json" v=""
  [ -f "$m" ] || { echo ""; return 0; }
  if command -v plutil >/dev/null 2>&1; then
    v="$(plutil -extract version raw -o - "$m" 2>/dev/null || true)"
  fi
  if [ -z "$v" ] && command -v python3 >/dev/null 2>&1; then
    v="$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1])).get("version", ""))' "$m" 2>/dev/null || true)"
  fi
  if [ -z "$v" ]; then
    v="$(sed -n 's/^  "version": *"\([^"]*\)".*/\1/p' "$m" | head -1)"
  fi
  echo "$v"
}

# patch(1) wrappers. -f: never ask and never guess that a patch is reversed.
# -F 0: no fuzz, every context line must match exactly.
patch_fwd() { patch -f -N -F 0 $GNU_FLAGS -p1 -d "$EXT" -i "$PATCH_FILE" "$@"; }
patch_rev() { patch -f -R -F 0 $GNU_FLAGS -p1 -d "$EXT" -i "$PATCH_FILE" "$@"; }

# applied | patched-other | pristine | unknown
detect_state() {
  if patch_rev --dry-run >/dev/null 2>&1; then
    echo applied
  elif grep -qF "$MARKER" "$TARGET"; then
    echo patched-other
  elif patch_fwd --dry-run >/dev/null 2>&1; then
    echo pristine
  else
    echo unknown
  fi
}

backup() {
  local dir stamp dest
  dir="${MAC_MCP_PATCHES_BACKUP_DIR:-$HOME/.mac-mcp-patches/backups}/$PATCH_ID"
  mkdir -p "$dir"
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  dest="$dir/index.js.v${VERSION:-unknown}.$1.$stamp"
  cp -p "$TARGET" "$dest"
  cmp -s "$TARGET" "$dest" || fail 1 "backup copy does not match $TARGET"
  echo "$dest"
}

restore() {
  cp -p "$1" "$TARGET"
  echo "restored $TARGET from $1" >&2
}

# Syntax check with node when it is installed. The copy gets a .mjs name so
# node parses it as an ES module whatever package.json says.
syntax_check() {
  local tmp rc=0
  if ! command -v node >/dev/null 2>&1; then
    echo "node not found; skipped the syntax check"
    return 0
  fi
  tmp="$(mktemp -d)"
  cp "$TARGET" "$tmp/index.mjs"
  node --check "$tmp/index.mjs" || rc=$?
  rm -f "$tmp/index.mjs"; rmdir "$tmp" 2>/dev/null || true
  return $rc
}

run_patch() {
  local mode=apply ext="" state bak out
  while [ $# -gt 0 ]; do
    case "$1" in
      --check) mode=check ;;
      --revert) mode=revert ;;
      --ext-dir)
        shift
        [ $# -gt 0 ] || fail 2 "--ext-dir needs a folder"
        ext="$1" ;;
      -h|--help) usage; exit 0 ;;
      *) usage >&2; fail 2 "unknown option: $1" ;;
    esac
    shift
  done

  command -v patch >/dev/null 2>&1 || fail 2 "patch(1) not found"
  [ -f "$PATCH_FILE" ] || fail 2 "patch file missing: $PATCH_FILE"
  GNU_FLAGS=""
  case "$(patch --version 2>&1 || true)" in
    *GNU*) GNU_FLAGS="--no-backup-if-mismatch" ;;
  esac

  if [ -z "$ext" ]; then
    ext="$(find_extension)" || exit $?
  fi
  [ -d "$ext" ] || fail 2 "not a folder: $ext"
  EXT="$(cd "$ext" && pwd)"
  TARGET="$EXT/server/index.js"
  [ -f "$TARGET" ] || fail 2 "no server/index.js in $EXT"
  VERSION="$(read_version "$EXT")"
  state="$(detect_state)"

  echo "extension: $EXT"
  echo "installed version: ${VERSION:-unknown}; patch built for: $EXPECTED_VERSION; state: $state"

  case "$mode:$state" in
    *:applied)
      if [ "$mode" = revert ]; then
        bak="$(backup pre-revert)"
        out="$(patch_rev 2>&1)" || { restore "$bak"; fail 1 "reverse patch failed: $out"; }
        echo "reverted. Backup of the patched file: $bak"
        echo "Quit and reopen Claude so the extension reloads."
      else
        echo "patch already applied; nothing to do"
      fi
      exit 0 ;;
    *:patched-other)
      echo "the file has the patch marker but is not this exact patch's result."
      echo "It was patched by another build of this fix; nothing to do."
      [ "$mode" = revert ] && fail 1 "cannot reverse cleanly; restore a backup from ${MAC_MCP_PATCHES_BACKUP_DIR:-$HOME/.mac-mcp-patches/backups}/$PATCH_ID"
      exit 0 ;;
    revert:pristine)
      echo "patch is not applied; nothing to revert"
      exit 0 ;;
    revert:unknown)
      fail 1 "the file is neither patched nor upstream v$EXPECTED_VERSION; restore a backup by hand" ;;
    *:unknown)
      fail 1 "the patch does not apply cleanly to this file (version ${VERSION:-unknown}). Port it by hand, see docs/porting.md" ;;
  esac

  # state is pristine: the patch applies cleanly
  if [ "$VERSION" != "$EXPECTED_VERSION" ]; then
    fail 1 "installed version is ${VERSION:-unknown}, patch was built for $EXPECTED_VERSION. The diff applies, but the code around it may have changed. Port it by hand, see docs/porting.md"
  fi
  if [ "$mode" = check ]; then
    echo "check: the patch would apply cleanly"
    exit 0
  fi

  bak="$(backup pre-apply)"
  out="$(patch_fwd 2>&1)" || { restore "$bak"; fail 1 "patch failed: $out"; }
  if ! grep -qF "$MARKER" "$TARGET"; then
    restore "$bak"; fail 1 "marker missing after patching"
  fi
  if ! syntax_check; then
    restore "$bak"; fail 1 "node --check failed on the patched file"
  fi
  echo "patched. Backup of the original: $bak"
  echo "Quit and reopen Claude so the extension loads the new code."
}
