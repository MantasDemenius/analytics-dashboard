"""Blocks commits and pushes that would publish keys, private files or app-specific identifiers.

Run by the git hooks in `.githooks/`:
  check_secrets.py staged   scans what is staged for commit
  check_secrets.py push     scans every commit a push would publish (pre-push stdin)

Literal strings listed in the gitignored `config/forbidden.txt` (one per line) are blocked too.
"""

import re
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
    if argv == ["staged"]:
        findings = scan_staged(denylist)
    elif argv == ["push"]:
        findings = scan_push(sys.stdin.read().splitlines(), denylist)
    else:
        print("usage: check_secrets.py staged|push", file=sys.stderr)
        return 2
    for finding in findings:
        print(f"Blocked: {finding.path}: {finding.reason}", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
