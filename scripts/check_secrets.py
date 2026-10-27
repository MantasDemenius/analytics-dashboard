"""Blocks commits and pushes that would publish keys, private files or app-specific identifiers.

Run by the git hooks in `.githooks/` and the Claude Code hook in `.claude/settings.json`:
  check_secrets.py staged       scans what is staged for commit
  check_secrets.py push         scans every commit a push would publish (pre-push stdin)
  check_secrets.py text [FILE]  scans a file, or stdin, before it is posted anywhere public
  check_secrets.py gh-hook      scans a `gh issue|pr create|edit|comment` command and its
                                `--body-file` (PreToolUse event on stdin, exit 2 blocks it)

Literal strings listed in the gitignored `config/forbidden.txt` (one per line) are blocked too.
"""

import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DENYLIST_PATH = Path("config/forbidden.txt")
ZERO_SHA = "0" * 40

CONTENT_PATTERNS = {
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "service account key field": re.compile(r'"private_key(_id)?"\s*:'),
    "Google API key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "OAuth client secret": re.compile(r"GOCSPX-[0-9A-Za-z_\-]{20,}"),
    "OAuth client secret field": re.compile(r'"client_secret"\s*:'),
    "OAuth refresh token": re.compile(r"1//0[0-9A-Za-z_\-]{20,}"),
    "OAuth access token": re.compile(r"ya29\.[0-9A-Za-z_\-]{20,}"),
    "AdMob ID": re.compile(r"\bpub-\d{16}\b"),
    "service account email": re.compile(r"[\w.\-]+@[\w\-]+\.iam\.gserviceaccount\.com"),
}

PRIVATE_PATH_PATTERNS = {
    "private folder": re.compile(r"^(config|history|out)/"),
    "PDF report": re.compile(r"\.pdf$"),
    "HTML outside templates/": re.compile(r"^(?!templates/).*\.html$"),
    "key or token file": re.compile(
        r"(service-account|credentials|client_secret|token)[^/]*\.json$"
    ),
    "env file": re.compile(r"(^|/)\.env(\.[^/]*)?$"),
}


GH_WRITE_COMMAND = re.compile(r"\bgh(\.exe)?\s+(issue|pr)\s+(create|edit|comment)\b")
BODY_FILE_FLAGS = ("--body-file", "-F")
MSYS_DRIVE_PATH = re.compile(r"^/([a-zA-Z])/")
GH_LABEL = "gh command"


@dataclass(frozen=True)
class Finding:
    path: str
    reason: str


def load_denylist(path: Path) -> list[str]:
    if not path.is_file():
        return []
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return [line.lower() for line in lines if line and not line.startswith("#")]


def line_reason(line: str, denylist: list[str]) -> str | None:
    for reason, pattern in CONTENT_PATTERNS.items():
        if pattern.search(line):
            return reason
    lowered = line.lower()
    for entry in denylist:
        if entry in lowered:
            return f"denylisted '{entry}'"
    return None


def scan_diff(diff: str, denylist: list[str]) -> list[Finding]:
    findings = []
    path = ""
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("+"):
            reason = line_reason(line[1:], denylist)
            if reason:
                findings.append(Finding(path, reason))
    return findings


def scan_text(label: str, text: str, denylist: list[str]) -> list[Finding]:
    reasons = (line_reason(line, denylist) for line in text.splitlines())
    return [Finding(label, reason) for reason in reasons if reason]


def scan_paths(paths: list[str]) -> list[Finding]:
    findings = []
    for path in paths:
        for reason, pattern in PRIVATE_PATH_PATTERNS.items():
            if pattern.search(path):
                findings.append(Finding(path, reason))
                break
    return findings


def unquote(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]
    return token


def body_file_args(command: str) -> list[str]:
    tokens = shlex.split(command, posix=False)
    args = []
    for index, token in enumerate(tokens):
        if token in BODY_FILE_FLAGS:
            args.append(unquote(tokens[index + 1]) if index + 1 < len(tokens) else "")
        elif token.startswith("--body-file="):
            args.append(unquote(token.removeprefix("--body-file=")))
    return args


def scan_body_file(arg: str, cwd: Path, denylist: list[str]) -> list[Finding]:
    if arg in ("", "-"):
        return [Finding(GH_LABEL, "body from stdin; pass a file to --body-file")]
    path = cwd / MSYS_DRIVE_PATH.sub(r"\1:/", arg)
    if not path.is_file():
        return [Finding(arg, "body file not found, so it cannot be scanned")]
    return scan_text(arg, path.read_text(encoding="utf-8"), denylist)


def scan_gh_command(command: str, cwd: Path, denylist: list[str]) -> list[Finding]:
    if not GH_WRITE_COMMAND.search(command):
        return []
    if "\n" in command.strip():
        return [Finding(GH_LABEL, "spans more than one line; use --body-file")]
    try:
        args = body_file_args(command)
    except ValueError:
        return [Finding(GH_LABEL, "cannot be parsed, so it cannot be scanned")]
    findings = scan_text(GH_LABEL, command, denylist)
    for arg in args:
        findings += scan_body_file(arg, cwd, denylist)
    return findings


def read_stdin() -> str:
    return sys.stdin.buffer.read().decode("utf-8")


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout


def scan_staged(denylist: list[str]) -> list[Finding]:
    paths = git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines()
    diff = git("diff", "--cached", "--unified=0", "--no-color", "--diff-filter=ACMR")
    return scan_paths(paths) + scan_diff(diff, denylist)


def scan_commit(sha: str, denylist: list[str]) -> list[Finding]:
    paths = git(
        "diff-tree",
        "--root",
        "--no-commit-id",
        "--name-only",
        "-r",
        "--diff-filter=ACMR",
        sha,
    )
    diff = git(
        "show", "--format=", "--unified=0", "--no-color", "--diff-filter=ACMR", sha
    )
    message = git("log", "-1", "--format=%B", sha)
    return (
        scan_paths(paths.splitlines())
        + scan_diff(diff, denylist)
        + scan_text(f"commit {sha[:7]} message", message, denylist)
    )


def scan_push(push_lines: list[str], denylist: list[str]) -> list[Finding]:
    findings = []
    for line in push_lines:
        parts = line.split()
        if len(parts) != 4 or parts[1] == ZERO_SHA:
            continue
        for sha in git("rev-list", parts[1], "--not", "--remotes").splitlines():
            findings += scan_commit(sha, denylist)
    return findings


def main(argv: list[str]) -> int:
    denylist = load_denylist(DENYLIST_PATH)
    blocked_code = 1
    if argv == ["staged"]:
        findings = scan_staged(denylist)
    elif argv == ["push"]:
        findings = scan_push(read_stdin().splitlines(), denylist)
    elif argv == ["text"]:
        findings = scan_text("stdin", read_stdin(), denylist)
    elif len(argv) == 2 and argv[0] == "text":
        findings = scan_text(
            argv[1], Path(argv[1]).read_text(encoding="utf-8"), denylist
        )
    elif argv == ["gh-hook"]:
        event = json.loads(read_stdin())
        command = event["tool_input"]["command"]
        findings = scan_gh_command(command, Path(event["cwd"]), denylist)
        blocked_code = 2
    else:
        print(
            "usage: check_secrets.py staged|push|text [FILE]|gh-hook", file=sys.stderr
        )
        return 2
    for finding in findings:
        print(f"Blocked: {finding.path}: {finding.reason}", file=sys.stderr)
    return blocked_code if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
