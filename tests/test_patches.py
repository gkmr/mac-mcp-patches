"""Tests for mac-mcp-patches. Python 3 stdlib only, no network.

Always run: patch file structure, script syntax, and the apply-patch.sh guards
against synthetic extension folders (not found, two matches, wrong version,
wrong content, already patched).

Run only when you supply the pristine upstream server/index.js (this repo does
not ship it; no license is stated in its header):
  MCP_PATCHES_IMESSAGE_ORIG=/path/to/index.js   (v0.1.11)
  MCP_PATCHES_NOTES_ORIG=/path/to/index.js      (v0.1.7)
or drop the files at tests/upstream/imessage/index.js and tests/upstream/notes/index.js
(git-ignored). Those tests run `patch --dry-run` against the real file and then a
full apply, re-apply, check and revert cycle on a temp copy.

Run: python3 -m unittest discover -s tests -v
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PATCHES = {
    "imessage": {
        "script": "patches/imessage/apply-patch.sh",
        "patch": "patches/imessage/imessage-v0.1.11-fast-search-sms-fallback.patch",
        "version": "0.1.11",
        "fingerprint": 'name: "iMessage-AppleScript-Server"',
        "marker": "searchContactsSQLite",
        "env": "MCP_PATCHES_IMESSAGE_ORIG",
        "orig_sha256": "b5d0a4fa292720d1d5f91a38a162ad3d87273d9bf48b13757268d4d34add0e1a",
        "example": "examples/fake-extensions/imessage",
    },
    "notes": {
        "script": "patches/notes/apply-patch.sh",
        "patch": "patches/notes/notes-v0.1.7-bulk-list-timeouts.patch",
        "version": "0.1.7",
        "fingerprint": 'name: "Apple-Notes-Server"',
        "marker": "Patched 2026-07-07",
        "env": "MCP_PATCHES_NOTES_ORIG",
        "orig_sha256": "f4253c34f352ab0a86dcbe0adb0a37f52c1b50cfd3d3d8aa741c328f5950de9d",
        "example": "examples/fake-extensions/notes",
    },
}

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def upstream_file(pid):
    cfg = PATCHES[pid]
    p = os.environ.get(cfg["env"]) or os.path.join(REPO, "tests", "upstream", pid, "index.js")
    return p if os.path.isfile(p) else None


def parse_patch(text):
    """Return (header_lines, hunks). Each hunk: dict(old_start, old_n, new_start, new_n, lines)."""
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("--- "))
    header = lines[start:start + 2]
    hunks, i = [], start + 2
    while i < len(lines):
        m = HUNK_RE.match(lines[i])
        if not m:
            raise AssertionError("expected a hunk header at line %d: %r" % (i + 1, lines[i]))
        old_n = int(m.group(2) or 1)
        new_n = int(m.group(4) or 1)
        i += 1
        o = n = 0
        body = []
        while i < len(lines) and (o < old_n or n < new_n):
            ln = lines[i]
            tag = ln[:1]
            if tag == " ":
                o += 1; n += 1
            elif tag == "-":
                o += 1
            elif tag == "+":
                n += 1
            elif tag != "\\":
                raise AssertionError("bad hunk line %d: %r" % (i + 1, ln))
            body.append(ln)
            i += 1
        if (o, n) != (old_n, new_n):
            raise AssertionError("hunk at %s counts %d/%d, header says %d/%d" % (m.group(0), o, n, old_n, new_n))
        hunks.append({"old_start": int(m.group(1)), "old_n": old_n, "new_start": int(m.group(3)),
                      "new_n": new_n, "lines": body})
    return header, hunks


class Sandbox:
    """A temp extensions root plus a temp backup dir, so nothing touches the real home folder."""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="mmp-test-")
        self.root = os.path.join(self.dir, "Claude Extensions")
        self.backups = os.path.join(self.dir, "backups")
        os.makedirs(self.root)

    def add_extension(self, name, version, index_js_text=None, index_js_path=None):
        ext = os.path.join(self.root, name)
        os.makedirs(os.path.join(ext, "server"))
        with open(os.path.join(ext, "manifest.json"), "w") as f:
            json.dump({"name": name, "version": version}, f, indent=2)
        dst = os.path.join(ext, "server", "index.js")
        if index_js_path:
            shutil.copyfile(index_js_path, dst)
        else:
            with open(dst, "w") as f:
                f.write(index_js_text)
        return ext

    def run(self, pid, *args):
        env = dict(os.environ, CLAUDE_EXTENSIONS_DIR=self.root, MAC_MCP_PATCHES_BACKUP_DIR=self.backups)
        p = subprocess.run(["bash", os.path.join(REPO, PATCHES[pid]["script"])] + list(args),
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, universal_newlines=True,
                           timeout=60)
        return p.returncode, p.stdout

    def backup_files(self, pid):
        d = os.path.join(self.backups, pid)
        return sorted(os.listdir(d)) if os.path.isdir(d) else []

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


class PatchFileTests(unittest.TestCase):
    def test_patch_structure(self):
        for pid, cfg in PATCHES.items():
            with self.subTest(pid=pid):
                text = read(os.path.join(REPO, cfg["patch"]))
                header, hunks = parse_patch(text)
                self.assertEqual(header, ["--- a/server/index.js", "+++ b/server/index.js"])
                self.assertGreater(len(hunks), 0)
                added = [ln[1:] for h in hunks for ln in h["lines"] if ln.startswith("+")]
                kept_or_removed = [ln[1:] for h in hunks for ln in h["lines"] if ln[:1] in (" ", "-")]
                self.assertTrue(any(cfg["marker"] in ln for ln in added), "marker must be added by the patch")
                self.assertFalse(any(cfg["marker"] in ln for ln in kept_or_removed), "marker must be new")
                removed = [ln[1:] for h in hunks for ln in h["lines"] if ln.startswith("-")]
                self.assertFalse(any(cfg["fingerprint"] in ln for ln in removed),
                                 "the patch must not remove the fingerprint the script searches for")
                starts = [h["old_start"] for h in hunks]
                self.assertEqual(starts, sorted(starts), "hunks must be in file order")

    def test_patch_names_its_version(self):
        for pid, cfg in PATCHES.items():
            with self.subTest(pid=pid):
                self.assertIn("v" + cfg["version"], os.path.basename(cfg["patch"]))
                script = read(os.path.join(REPO, cfg["script"]))
                self.assertIn('EXPECTED_VERSION="%s"' % cfg["version"], script)
                self.assertIn(os.path.basename(cfg["patch"]), script)

    def test_scripts_parse_and_have_no_personal_paths(self):
        scripts = [os.path.join(REPO, c["script"]) for c in PATCHES.values()]
        scripts.append(os.path.join(REPO, "lib", "apply-common.sh"))
        for s in scripts:
            with self.subTest(script=os.path.relpath(s, REPO)):
                p = subprocess.run(["bash", "-n", s], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                self.assertEqual(p.returncode, 0, p.stdout)
                self.assertNotIn("/Users/", read(s))


class GuardTests(unittest.TestCase):
    """apply-patch.sh must refuse anything that is not exactly the upstream file it was built for."""

    def setUp(self):
        self.sb = Sandbox()

    def tearDown(self):
        self.sb.close()

    def fake_js(self, pid, extra=""):
        return "// synthetic\nconst s = { %s };\n%s" % (PATCHES[pid]["fingerprint"], extra)

    def test_not_found(self):
        for pid in PATCHES:
            with self.subTest(pid=pid):
                rc, out = self.sb.run(pid)
                self.assertEqual(rc, 2, out)
                self.assertIn("no ", out)

    def test_two_matches_need_ext_dir(self):
        for pid in PATCHES:
            with self.subTest(pid=pid):
                a = self.sb.add_extension(pid + "-a", PATCHES[pid]["version"], self.fake_js(pid))
                b = self.sb.add_extension(pid + "-b", PATCHES[pid]["version"], self.fake_js(pid))
                rc, out = self.sb.run(pid)
                self.assertEqual(rc, 2, out)
                self.assertIn(a, out)
                self.assertIn(b, out)

    def test_wrong_version_refused_and_untouched(self):
        for pid in PATCHES:
            with self.subTest(pid=pid):
                ext = self.sb.add_extension(pid + "-old", "9.9.9", self.fake_js(pid))
                before = sha256(os.path.join(ext, "server", "index.js"))
                rc, out = self.sb.run(pid)
                self.assertEqual(rc, 1, out)
                self.assertEqual(before, sha256(os.path.join(ext, "server", "index.js")))
                self.assertEqual(self.sb.backup_files(pid), [])

    def test_right_version_wrong_content_refused(self):
        for pid in PATCHES:
            with self.subTest(pid=pid):
                ext = self.sb.add_extension(pid + "-edited", PATCHES[pid]["version"], self.fake_js(pid))
                before = sha256(os.path.join(ext, "server", "index.js"))
                rc, out = self.sb.run(pid)
                self.assertEqual(rc, 1, out)
                self.assertIn("does not apply cleanly", out)
                self.assertEqual(before, sha256(os.path.join(ext, "server", "index.js")))

    def test_marker_means_nothing_to_do(self):
        for pid in PATCHES:
            with self.subTest(pid=pid):
                js = self.fake_js(pid, "// %s\n" % PATCHES[pid]["marker"])
                ext = self.sb.add_extension(pid + "-patched", PATCHES[pid]["version"], js)
                rc, out = self.sb.run(pid, "--ext-dir", ext)
                self.assertEqual(rc, 0, out)
                self.assertIn("nothing to do", out)
                self.assertEqual(read(os.path.join(ext, "server", "index.js")), js)

    def test_examples_are_found_and_refused(self):
        for pid, cfg in PATCHES.items():
            with self.subTest(pid=pid):
                rc, out = self.sb.run(pid, "--check", "--ext-dir", os.path.join(REPO, cfg["example"]))
                self.assertEqual(rc, 1, out)
                self.assertIn("installed version: 0.0.0-example", out)

    def test_unknown_option(self):
        rc, out = self.sb.run("notes", "--bogus")
        self.assertEqual(rc, 2, out)


class UpstreamTests(unittest.TestCase):
    """Need the pristine upstream file; skipped otherwise (see the module docstring)."""

    def setUp(self):
        self.sb = Sandbox()

    def tearDown(self):
        self.sb.close()

    def need(self, pid):
        p = upstream_file(pid)
        if not p:
            self.skipTest("upstream %s server/index.js v%s not supplied (set %s)"
                          % (pid, PATCHES[pid]["version"], PATCHES[pid]["env"]))
        self.assertEqual(sha256(p), PATCHES[pid]["orig_sha256"],
                         "%s is not the upstream v%s file this patch was built against" % (p, PATCHES[pid]["version"]))
        return p

    def check_dry_run(self, pid):
        orig = self.need(pid)
        d = tempfile.mkdtemp(prefix="mmp-dry-")
        try:
            os.makedirs(os.path.join(d, "server"))
            shutil.copyfile(orig, os.path.join(d, "server", "index.js"))
            p = subprocess.run(["patch", "--dry-run", "-f", "-N", "-F", "0", "-p1", "-d", d,
                                "-i", os.path.join(REPO, PATCHES[pid]["patch"])],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            self.assertEqual(p.returncode, 0, p.stdout)
            for bad in ("FAILED", "fuzz", "offset", "reject"):
                self.assertNotIn(bad, p.stdout)
            self.assertEqual(sha256(os.path.join(d, "server", "index.js")), PATCHES[pid]["orig_sha256"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def check_cycle(self, pid):
        orig = self.need(pid)
        cfg = PATCHES[pid]
        ext = self.sb.add_extension("ext-" + pid, cfg["version"], index_js_path=orig)
        target = os.path.join(ext, "server", "index.js")

        rc, out = self.sb.run(pid, "--check")
        self.assertEqual(rc, 0, out)
        self.assertIn("would apply cleanly", out)
        self.assertEqual(sha256(target), cfg["orig_sha256"])

        rc, out = self.sb.run(pid)
        self.assertEqual(rc, 0, out)
        self.assertIn("patched.", out)
        self.assertIn(cfg["marker"], read(target))
        backups = self.sb.backup_files(pid)
        self.assertEqual(len(backups), 1)
        self.assertEqual(sha256(os.path.join(self.sb.backups, pid, backups[0])), cfg["orig_sha256"])
        patched_sha = sha256(target)

        rc, out = self.sb.run(pid)
        self.assertEqual(rc, 0, out)
        self.assertIn("already applied", out)
        self.assertEqual(sha256(target), patched_sha)

        rc, out = self.sb.run(pid, "--revert")
        self.assertEqual(rc, 0, out)
        self.assertEqual(sha256(target), cfg["orig_sha256"])

        rc, out = self.sb.run(pid, "--revert")
        self.assertEqual(rc, 0, out)
        self.assertIn("nothing to revert", out)

    def check_version_guard_on_real_file(self, pid):
        orig = self.need(pid)
        ext = self.sb.add_extension("ext-new-" + pid, "0.2.0", index_js_path=orig)
        rc, out = self.sb.run(pid)
        self.assertEqual(rc, 1, out)
        self.assertIn("Port it by hand", out)
        self.assertEqual(sha256(os.path.join(ext, "server", "index.js")), PATCHES[pid]["orig_sha256"])

    def test_imessage_dry_run_applies_cleanly(self):
        self.check_dry_run("imessage")

    def test_notes_dry_run_applies_cleanly(self):
        self.check_dry_run("notes")

    def test_imessage_apply_reapply_revert(self):
        self.check_cycle("imessage")

    def test_notes_apply_reapply_revert(self):
        self.check_cycle("notes")

    def test_imessage_refuses_newer_version_even_if_diff_applies(self):
        self.check_version_guard_on_real_file("imessage")

    def test_notes_refuses_newer_version_even_if_diff_applies(self):
        self.check_version_guard_on_real_file("notes")


if __name__ == "__main__":
    unittest.main()
