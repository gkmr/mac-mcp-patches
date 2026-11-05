# Porting a patch to a new extension version

Claude desktop replaces `server/index.js` when an extension updates. `apply-patch.sh` then reports a version mismatch, or "does not apply cleanly", and changes nothing. That refusal is on purpose: a diff can apply with matching context lines while the code around it changed meaning.

To port:

1. Save a copy of the new upstream file before touching it, for example `tests/upstream/<name>/index.js` (git-ignored).
2. Check whether the new version already fixes the bug. Read the changed functions: `runAppleScript`, `search_contacts`, `send_imessage` (iMessage) or `list_notes`, `get_note_content` (Notes).
3. Try the old diff on a copy: `patch --dry-run -p1 -d <copy-of-extension> -i patches/<name>/<file>.patch`. If it applies, read every hunk against the new code anyway.
4. Make the edits by hand on the copy, then write a new diff from the extension folder's parent:
   `diff -u --label a/server/index.js --label b/server/index.js old/server/index.js new/server/index.js`
5. Save it as `patches/<name>/<name>-v<new version>-<what>.patch`, keep the text header at the top, and update `EXPECTED_VERSION`, `PATCH_FILE` and, if the marker moved, `MARKER` in that folder's `apply-patch.sh`.
6. Update the version, file name and upstream sha256 in `tests/test_patches.py`, then run the tests with the new upstream file supplied. All upstream tests must pass, not skip.
