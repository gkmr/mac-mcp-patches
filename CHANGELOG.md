# Changelog

## 1.0.0 (2026-11-05)
- First public version. Two patches as unified diffs: iMessage extension v0.1.11 (fast contact search, SMS fallback, timeouts) and Apple Notes extension v0.1.7 (bulk `list_notes`, contains-match `get_note_content`, timeouts).
- `apply-patch.sh` per patch, sharing `lib/apply-common.sh`: finds the extension by a fingerprint, checks the manifest version, decides with `patch --dry-run` (forward and reverse), backs up, applies with zero fuzz, runs `node --check`, restores on failure. Adds `--check` and `--revert`.
- Tests: 10 that always run, 6 that run when the upstream file is supplied.

## 0.x (2026-07-07, private)
- Full patched files copied over the extension, guarded by a version string and a marker grep.
