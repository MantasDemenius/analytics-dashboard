import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_secrets

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_secrets.py"

FAKE_SECRETS = {
    "private key block": "-----BEGIN " + "PRIVATE KEY-----",
    "service account key field": '"private' + '_key": "abc"',
    "service account key id field": '"private' + '_key_id": "abc"',
    "Google API key": "AIza" + "A" * 35,
    "OAuth client secret": "GOCSPX-" + "a" * 28,
    "OAuth client secret field": '"client' + '_secret": "abc"',
    "OAuth refresh token": "1//0" + "a" * 40,
    "OAuth access token": "ya29." + "a" * 40,
    "AdMob app ID": "ca-app-" + "pub-" + "1" * 16 + "~" + "2" * 10,
    "AdMob publisher ID": "pub-" + "1" * 16,
    "service account email": "bot@proj" + ".iam.gserviceaccount.com",
}


def diff_adding(path, *lines):
    added = "\n".join("+" + line for line in lines)
    return f"diff --git a/{path} b/{path}\n--- /dev/null\n+++ b/{path}\n@@ -0,0 +1 @@\n{added}\n"


class ScanDiffTest(unittest.TestCase):
    def test_every_built_in_pattern_is_caught(self):
        for name, secret in FAKE_SECRETS.items():
            with self.subTest(name):
                findings = check_secrets.scan_diff(diff_adding("a.txt", "x = " + secret), [])
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0].path, "a.txt")

    def test_clean_diff_passes(self):
        self.assertEqual(check_secrets.scan_diff(diff_adding("a.py", "print('hello')"), []), [])

    def test_empty_diff_passes(self):
        self.assertEqual(check_secrets.scan_diff("", []), [])

    def test_removed_lines_are_ignored(self):
        diff = "+++ b/a.txt\n-" + FAKE_SECRETS["Google API key"] + "\n"
        self.assertEqual(check_secrets.scan_diff(diff, []), [])

    def test_placeholder_ids_pass(self):
        diff = diff_adding("config.example.yaml", "admob_app_id: ca-app-pub-XXXXXXXXXXXXXXXX~YYYYYYYYYY")
        self.assertEqual(check_secrets.scan_diff(diff, []), [])

    def test_denylist_entry_is_caught_ignoring_case(self):
        findings = check_secrets.scan_diff(diff_adding("docs/a.md", "The MyApp report"), ["myapp"])
        self.assertEqual(len(findings), 1)
        self.assertIn("myapp", findings[0].reason)

    def test_findings_are_attributed_to_their_file(self):
        diff = diff_adding("clean.md", "fine") + diff_adding("dirty.md", FAKE_SECRETS["OAuth access token"])
        self.assertEqual([f.path for f in check_secrets.scan_diff(diff, [])], ["dirty.md"])


class ScanPathsTest(unittest.TestCase):
    def test_private_paths_are_caught(self):
        for path in [
            "config/apps.md",
            "history/2026-10-26.json",
            "out/report.html",
            "report.pdf",
            "report.html",
            "keys/play-service-account.json",
            "credentials.json",
            "client_secret_123.json",
            "token.json",
            ".env",
            ".env.local",
        ]:
            with self.subTest(path):
                self.assertEqual(len(check_secrets.scan_paths([path])), 1)

    def test_public_paths_pass(self):
        paths = ["templates/report.html", "config.example.yaml", "src/token_store.py", "docs/decisions.md"]
        self.assertEqual(check_secrets.scan_paths(paths), [])

    def test_no_paths_pass(self):
        self.assertEqual(check_secrets.scan_paths([]), [])


class LoadDenylistTest(unittest.TestCase):
    def test_missing_file_gives_empty_list(self):
        self.assertEqual(check_secrets.load_denylist(Path("does/not/exist.txt")), [])

    def test_blank_lines_and_comments_are_skipped_and_entries_lowercased(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "forbidden.txt"
            path.write_text("# apps\n\nMyApp\n  other-id  \n", encoding="utf-8")
            self.assertEqual(check_secrets.load_denylist(path), ["myapp", "other-id"])


class HookCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.git("init", "-q")
        (self.repo / "config").mkdir()
        (self.repo / "config" / "forbidden.txt").write_text("myapp\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
            cwd=self.repo, check=True, capture_output=True,
        )

    def stage(self, name, content):
        (self.repo / name).write_text(content, encoding="utf-8")
        self.git("add", name)

    def run_script(self, *args, stdin=""):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args], cwd=self.repo, input=stdin, capture_output=True, text=True,
        )

    def test_staged_clean_file_passes(self):
        self.stage("a.md", "hello\n")
        self.assertEqual(self.run_script("staged").returncode, 0)

    def test_staged_secret_blocks(self):
        self.stage("a.md", FAKE_SECRETS["Google API key"] + "\n")
        result = self.run_script("staged")
        self.assertEqual(result.returncode, 1)
        self.assertIn("a.md", result.stderr)

    def test_staged_denylist_entry_blocks(self):
        self.stage("a.md", "about MyApp\n")
        self.assertEqual(self.run_script("staged").returncode, 1)

    def test_force_added_private_path_blocks(self):
        self.git("add", "-f", "config/forbidden.txt")
        self.assertEqual(self.run_script("staged").returncode, 1)

    def test_push_blocks_secret_in_an_earlier_unpushed_commit(self):
        self.stage("a.md", FAKE_SECRETS["OAuth refresh token"] + "\n")
        self.git("commit", "-q", "-m", "first")
        self.stage("a.md", "cleaned\n")
        self.git("commit", "-q", "-m", "second")
        self.assertEqual(self.run_script("push", stdin=self.push_line()).returncode, 1)

    def test_push_blocks_secret_in_commit_message(self):
        self.stage("a.md", "hello\n")
        self.git("commit", "-q", "-m", "fix for " + FAKE_SECRETS["AdMob publisher ID"])
        self.assertEqual(self.run_script("push", stdin=self.push_line()).returncode, 1)

    def test_push_of_clean_commits_passes(self):
        self.stage("a.md", "hello\n")
        self.git("commit", "-q", "-m", "clean")
        self.assertEqual(self.run_script("push", stdin=self.push_line()).returncode, 0)

    def test_branch_deletion_passes(self):
        line = "(delete) " + "0" * 40 + " refs/heads/old " + "1" * 40 + "\n"
        self.assertEqual(self.run_script("push", stdin=line).returncode, 0)

    def push_line(self):
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.repo, check=True, capture_output=True, text=True,
        ).stdout.strip()
        return f"refs/heads/master {sha} refs/heads/master {'0' * 40}\n"


if __name__ == "__main__":
    unittest.main()
