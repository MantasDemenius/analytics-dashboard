# CLAUDE.md

A Python command line tool (managed by uv) that pulls a week of metrics for the author's Android
apps (Play Console, Crashlytics, Firestore feedback, AdMob, later Google Analytics), renders one
HTML report with charts, prints it to PDF with headless Chrome and emails it through the Gmail API.
Runs on the author's PC every Monday via Windows Task Scheduler. Apps join through config.

**No code exists yet.** Read `docs/decisions.md` before anything else: it holds every decision
made so far, the rejected options, the unverified facts to check first, and the open questions.
Then read the gitignored `config/apps.md`, which names the apps and their identifiers. The next
step is a spec in this folder, starting with a prototype ticket for the HTML design.

**This repo is public** (https://github.com/MantasDemenius/analytics-dashboard). Config, keys,
tokens, history and generated reports live inside the local repo in gitignored paths
(`.gitignore` lists them) and must never be committed. A generated report holds users' feedback
text and emails, so leaking one is a privacy incident, not just a key leak. If a key is ever
committed, revoke it; deleting the commit is not enough. Nothing app-specific goes in the repo
either, docs and tests included: no app names, package names, Firebase project IDs, AdMob IDs or
paths into the apps' repos. Those live only in `config/`.

Git hooks in `.githooks/` enforce this: `scripts/check_secrets.py` blocks commits and pushes carrying
keys, tokens, private paths, AdMob IDs or any string listed in the gitignored `config/forbidden.txt`.
A fresh clone needs `git config core.hooksPath .githooks`. Never bypass them; add new app
identifiers to `config/forbidden.txt` when an app joins.

Other hard constraints, detailed in `docs/decisions.md`: free only (no billing, no Claude tokens on
the weekly run), review and feedback text never stored, history kept as numbers only, new packages
agreed with the author first.
