# Apple Notes patch: bulk list, contains-match read, timeouts

Patch: `patches/notes/notes-v0.1.7-bulk-list-timeouts.patch`

| | |
|---|---|
| Upstream | "Read and Write Apple Notes", a Claude desktop extension. File `server/index.js`, MCP server name `Apple-Notes-Server` |
| Version | extension manifest 0.1.7 |
| License | not stated in the `server/index.js` header, so this repo ships only the diff, not the file |
| Size | 6 hunks, 64 lines added, 8 removed |
| Marker | `Patched 2026-07-07` |

## Bug 1: `list_notes` is slow and can return broken JSON

**Symptom.** `list_notes` was slow on a large library and sometimes returned text that did not parse as JSON.

**Root cause.** The upstream AppleScript fetches every note reference, then loops and reads `name`, `id`, `creation date` and `modification date` one note at a time: 4 Apple Events per listed note. It builds JSON by gluing strings together inside AppleScript, with no escaping, so a title with a double quote or a backslash produces invalid JSON.

**Fix.**
- Bulk fetch: `name of notes`, `id of notes`, `creation date of notes`, `modification date of notes`. That is 4 Apple Events in total, whatever the limit or library size.
- AppleScript joins fields with the ASCII unit separator (code 31) and records with the record separator (code 30). JavaScript splits them and builds the result with `JSON.stringify`, so titles cannot break the output.
- Capped at 45 seconds. The original loop stays below as a fallback, also capped at 45 seconds.
- Output is pretty-printed JSON. Compact one-line output means the old code is still running.

## Bug 2: `get_note_content` misses notes whose titles are not an exact match

**Symptom.** Asking for "Weekly Plan" fails when the note is titled with an emoji in front, such as "🗓 Weekly Plan".

**Root cause.** Upstream only uses `first note whose name is <title>`.

**Fix.** Try the exact match first. On error, fall back to `first note whose name contains <title>`. Capped at 30 seconds.

`update_note_content` stays exact-match only on purpose. A fuzzy match is fine for a read, but for a write it could overwrite the wrong note.

## Bug 3: no timeouts anywhere

**Root cause.** Same as the iMessage server: `runAppleScript()` had no timeout, so a stalled Notes app stalled the tool.

**Fix.** The same optional `timeoutMs` argument with `SIGKILL`. `add_note` and `update_note_content` get 30 seconds.

## Tradeoffs

- The bulk path assumes Notes returns the four property lists in the same order. It does in practice, and the fields stay paired because they come from the same `notes` collection in one script run.
- The bulk fetch reads every note's name and dates, then trims to the limit. For a huge library and a limit of 5 this reads more data than the loop did, but data is cheap and round trips are not.
- A title that contains character 30 or 31 would split wrongly. I have never seen one.
- The contains fallback returns the first match. If several titles contain the text, you get one of them.
