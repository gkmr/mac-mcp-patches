# iMessage patch: fast contact search, SMS fallback, timeouts

Patch: `patches/imessage/imessage-v0.1.11-fast-search-sms-fallback.patch`

| | |
|---|---|
| Upstream | "Read and Send iMessages", a Claude desktop extension. File `server/index.js`, MCP server name `iMessage-AppleScript-Server` |
| Version | extension manifest 0.1.11 |
| License | not stated in the `server/index.js` header, so this repo ships only the diff, not the file |
| Size | 7 hunks, 167 lines added, 11 removed |
| Marker | `searchContactsSQLite` (only the patched file has it) |

## Bug 1: `search_contacts` never returns

**Symptom.** Every `search_contacts` call timed out. With thousands of contacts in my address book, the tool hit the 60 second MCP timeout on every query, so the model could not turn a name into a phone number or email.

**Root cause.** The upstream code loops over `every person` in Contacts with AppleScript and reads `name of p` for each one. Each property read is a separate Apple Event round trip between `osascript` and Contacts, and matching people also read `phones` and `emails`. That is several thousand inter-process calls per search, and the cost grows with the size of the address book, not the size of the result. The JSON is also built by string concatenation, so a name with a double quote breaks the output.

**Fix.**
- New `searchContactsSQLite()` reads the AddressBook databases directly with `sqlite3 -readonly -json`: the main `AddressBook-v22.abcddb` plus one per account under `Sources/`.
- Each word of the query must match first name, last name, nickname, organization or an email. A word with 3 or more digits also matches phone numbers with spaces, dashes, dots and brackets stripped. Results are deduplicated across sources and capped at 50.
- Rows come back as JSON from `sqlite3` and are re-serialized with `JSON.stringify`, so quotes in names are safe.
- The AppleScript path stays as a fallback. It now asks Contacts to filter (`every person whose name contains ...`), which is one Apple Event instead of one per person, and it is capped at 25 seconds.

In my use the SQLite path answers in about 10 ms.

## Bug 2: the `contacts://all` resource has the same loop

**Symptom.** Reading the "All Contacts" resource hung the same way.

**Fix.** It uses `searchContactsSQLite("", 10000)` first. The AppleScript fallback is capped at 60 seconds.

## Bug 3: `send_imessage` fails for phone numbers and SMS-only recipients

**Symptom.** Sending to a number typed with brackets, spaces and dashes, or to someone without iMessage failed, and a stuck send could hang the tool.

**Root cause.** The upstream script sends to `buddy <recipient> of (service 1 whose service type = iMessage)` using the recipient string exactly as given. There is no SMS path, and formatting differences mean the handle does not match.

**Fix.**
- Phone recipients are cleaned to digits and `+`, and those with 10 or more digits go through the file's existing `normalizePhoneNumber()` (E.164, for example `+15550100000`). Email recipients are left alone.
- The script tries the iMessage account first, then the SMS account. SMS only works when Text Message Forwarding from an iPhone is on.
- The send is capped at 15 seconds and the reply says which service was used ("via iMessage" or "via SMS").

## Bug 4 (shared with the Notes patch): no timeout on `osascript`

**Root cause.** `runAppleScript()` called `execFile("osascript", ...)` with no timeout. If Contacts or Messages stalled, the tool call stalled with it.

**Fix.** `runAppleScript(script, timeoutMs = 0)` passes `{ timeout, killSignal: "SIGKILL" }` when a timeout is given. Calls without one behave as before.

## Tradeoffs

- The SQLite path depends on Apple's private AddressBook schema (`ZABCDRECORD`, `ZABCDPHONENUMBER`, `ZABCDEMAILADDRESS`). A macOS update could rename it. That is why the AppleScript fallback stays and why errors are logged, not thrown, per database.
- It needs Full Disk Access for the process that runs the server. The extension already needs that to read `chat.db`, so nothing new is granted.
- The SQL is built as a string because it goes through the `sqlite3` command line. Single quotes are doubled and the LIKE wildcards `%` and `_` (and `\`) are removed from user input, the database is opened `-readonly`, and `execFile` is used, so there is no shell.
- The SMS fallback can send by SMS when iMessage fails for a reason other than "not on iMessage". The reply names the service so the caller can tell.

## Verify by hand

After applying and restarting Claude, ask it to search contacts for a name you know. It should answer in a few seconds, with phones and emails as JSON.
