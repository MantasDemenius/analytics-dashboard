import json
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
                findings = check_secrets.scan_diff(
                    diff_adding("a.txt", "x = " + secret), []
                )
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0].path, "a.txt")

    def test_clean_diff_passes(self):
        self.assertEqual(
            check_secrets.scan_diff(diff_adding("a.py", "print('hello')"), []), []
        )

    def test_empty_diff_passes(self):
        self.assertEqual(check_secrets.scan_diff("", []), [])

    def test_removed_lines_are_ignored(self):
        diff = "+++ b/a.txt\n-" + FAKE_SECRETS["Google API key"] + "\n"
        self.assertEqual(check_secrets.scan_diff(diff, []), [])

    def test_placeholder_ids_pass(self):
        diff = diff_adding(
            "config.example.toml",
            'admob_app_id = "ca-app-pub-XXXXXXXXXXXXXXXX~YYYYYYYYYY"',
        )
        self.assertEqual(check_secrets.scan_diff(diff, []), [])

    def test_denylist_entry_is_caught_ignoring_case(self):
        findings = check_secrets.scan_diff(
            diff_adding("docs/a.md", "The MyApp report"), ["myapp"]
        )
        self.assertEqual(len(findings), 1)
        self.assertIn("myapp", findings[0].reason)

    def test_findings_are_attributed_to_their_file(self):
        diff = diff_adding("clean.md", "fine") + diff_adding(
            "dirty.md", FAKE_SECRETS["OAuth access token"]
        )
        self.assertEqual(
            [f.path for f in check_secrets.scan_diff(diff, [])], ["dirty.md"]
        )


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
        paths = [
            "templates/report.html",
            "config.example.toml",
            "src/token_store.py",
            "docs/decisions.md",
        ]
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


class ScanGhCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def scan(self, command, denylist=()):
        return check_secrets.scan_gh_command(command, self.cwd, list(denylist))

    def write_body(self, name, content):
        (self.cwd / name).write_text(content, encoding="utf-8")

    def test_read_only_gh_commands_pass(self):
        for command in ["gh issue view 3", "gh issue list --label needs-triage"]:
            with self.subTest(command):
                self.assertEqual(self.scan(command, ["myapp"]), [])

    def test_clean_issue_create_passes(self):
        self.assertEqual(
            self.scan('gh issue create --title "Add report" --body "One line"'), []
        )

    def test_secret_in_title_blocks(self):
        title = FAKE_SECRETS["Google API key"]
        self.assertEqual(len(self.scan(f'gh issue create --title "{title}"')), 1)

    def test_denylisted_word_blocks_ignoring_case(self):
        findings = self.scan('gh pr comment 4 --body "about MyApp"', ["myapp"])
        self.assertEqual(len(findings), 1)
        self.assertIn("myapp", findings[0].reason)

    def test_every_write_subcommand_is_scanned(self):
        for command in [
            "gh issue create",
            "gh issue edit 1",
            "gh issue comment 1",
            "gh pr create",
            "gh pr edit 1",
            "gh pr comment 1",
        ]:
            with self.subTest(command):
                self.assertEqual(
                    len(self.scan(command + " --body myapp", ["myapp"])), 1
                )

    def test_write_command_after_other_commands_is_scanned(self):
        command = "cd repo && gh issue create --title myapp"
        self.assertEqual(len(self.scan(command, ["myapp"])), 1)

    def test_multi_line_command_blocks(self):
        command = 'gh issue create --title "x" --body "first\nsecond"'
        self.assertIn("more than one line", self.scan(command)[0].reason)

    def test_clean_body_file_passes(self):
        self.write_body("body.md", "line one\nline two\n")
        self.assertEqual(self.scan("gh issue create --title x --body-file body.md"), [])

    def test_secret_in_body_file_blocks_in_every_flag_form(self):
        self.write_body("body.md", "fine\n" + FAKE_SECRETS["OAuth access token"] + "\n")
        for flag in ["--body-file body.md", "--body-file=body.md", "-F body.md"]:
            with self.subTest(flag):
                findings = self.scan(f"gh issue create --title x {flag}")
                self.assertEqual([f.path for f in findings], ["body.md"])

    def test_denylisted_word_in_body_file_blocks(self):
        self.write_body("body.md", "The MyApp report\n")
        self.assertEqual(
            len(self.scan("gh issue comment 2 --body-file body.md", ["myapp"])), 1
        )

    def test_quoted_body_file_path_with_spaces_is_read(self):
        self.write_body("my body.md", FAKE_SECRETS["AdMob publisher ID"])
        self.assertEqual(
            len(self.scan('gh issue create --title x --body-file "my body.md"')), 1
        )

    def test_absolute_body_file_path_is_read(self):
        path = self.cwd / "body.md"
        path.write_text(FAKE_SECRETS["AdMob publisher ID"], encoding="utf-8")
        command = f'gh issue create --title x --body-file "{path}"'
        self.assertEqual(len(check_secrets.scan_gh_command(command, Path("."), [])), 1)

    def test_msys_drive_path_is_read(self):
        path = self.cwd / "body.md"
        path.write_text(FAKE_SECRETS["AdMob publisher ID"], encoding="utf-8")
        drive, rest = path.as_posix().split(":", 1)
        command = f"gh issue create --title x --body-file /{drive.lower()}{rest}"
        self.assertEqual(len(check_secrets.scan_gh_command(command, Path("."), [])), 1)

    def test_missing_body_file_blocks(self):
        findings = self.scan("gh issue create --title x --body-file nope.md")
        self.assertIn("not found", findings[0].reason)

    def test_body_from_stdin_blocks(self):
        for command in [
            "gh issue create --title x --body-file -",
            "gh issue create --title x -F",
        ]:
            with self.subTest(command):
                self.assertEqual(len(self.scan(command)), 1)

    def test_unbalanced_quotes_block(self):
        findings = self.scan('gh issue create --title "x')
        self.assertIn("cannot be parsed", findings[0].reason)


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
            cwd=self.repo,
            check=True,
            capture_output=True,
        )

    def stage(self, name, content):
        (self.repo / name).write_text(content, encoding="utf-8")
        self.git("add", name)

    def run_script(self, *args, stdin=""):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            check=False,
            cwd=self.repo,
            input=stdin,
            capture_output=True,
            text=True,
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

    def test_text_file_with_secret_blocks(self):
        (self.repo / "body.md").write_text(
            FAKE_SECRETS["OAuth client secret"], encoding="utf-8"
        )
        result = self.run_script("text", "body.md")
        self.assertEqual(result.returncode, 1)
        self.assertIn("body.md", result.stderr)

    def test_text_from_stdin_uses_denylist(self):
        self.assertEqual(self.run_script("text", stdin="about MyApp\n").returncode, 1)
        self.assertEqual(self.run_script("text", stdin="hello\n").returncode, 0)

    def test_gh_hook_blocks_with_exit_code_2(self):
        result = self.run_script("gh-hook", stdin=self.hook_event("--title MyApp"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("myapp", result.stderr)

    def test_gh_hook_reads_body_file_from_event_cwd(self):
        body_dir = self.repo / "scratch"
        body_dir.mkdir()
        (body_dir / "body.md").write_text("about MyApp\n", encoding="utf-8")
        event = self.hook_event("--title x --body-file body.md", cwd=body_dir)
        self.assertEqual(self.run_script("gh-hook", stdin=event).returncode, 2)

    def test_gh_hook_allows_clean_command(self):
        result = self.run_script("gh-hook", stdin=self.hook_event("--title fine"))
        self.assertEqual(result.returncode, 0)

    def hook_event(self, args, cwd=None):
        return json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "gh issue create " + args},
                "cwd": str(cwd or self.repo),
            }
        )

    def push_line(self):
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return f"refs/heads/master {sha} refs/heads/master {'0' * 40}\n"


if __name__ == "__main__":
    unittest.main()
