# analytics-dashboard

A command line tool that pulls a week of metrics for the author's Android apps (Play Console,
Crashlytics, Firestore feedback, AdMob), renders one HTML report with charts, prints it to PDF with
headless Chrome and emails it through the Gmail API. Apps join through config; the keys are
documented in `config.example/`. Decisions and their reasons are in `docs/decisions.md`.

## Running it

```
uv run weekly-report [--from YYYY-MM-DD --to YYYY-MM-DD] [--email] [--no-open]
```

With no dates every source reports its newest complete Monday to Sunday week. `--email` prints the
PDF and mails it; `--no-open` leaves the report closed. The command line prints only the period,
the at a glance numbers, the problems and where the files went, never review or feedback text. It
exits non-zero when a source, the PDF or the email fails.

The weekly run is a Windows Task Scheduler task registered by `scripts/schedule_task.ps1`.

## Running it from the phone

The author runs it from the phone through Claude Code's Remote Control, in any Claude session open
on the PC, with a personal `/run-report [from] [to]` skill kept in the author's Claude config
folder (not in this repo, since it holds a local path). The skill runs:

```
uv run --directory <repo> weekly-report --email --no-open [--from <date> --to <date>]
```

and passes on only what that prints. It never opens the report files, so no user-written text
reaches a Claude transcript; the report itself arrives as the emailed PDF.
