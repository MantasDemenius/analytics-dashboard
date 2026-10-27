# Decisions so far

Outcome of a grilling session held on 2026-10-27, before this project had any code, and later
changes made in this repo (the language moved from Dart to Python on the same day). Nothing here is
specced yet. The unverified facts at the bottom are GitHub tickets, and everything else still to be
grilled and specced is on the pinned Roadmap issue.

App-specific details (which apps, their package names, Firebase projects, AdMob IDs, where their
own repos and docs live) are not in this repo. They are in the gitignored `config/apps.md` on the
author's PC.

## The problem

The author ships Android apps with data spread over Play Console, Firebase (Crashlytics, Firestore)
and AdMob. Each has its own console, so nobody looks at all of them regularly. The goal is one
weekly report covering every app, built so later apps plug in through config.

## What the report is

- A Python command line tool in this repo, managed by uv (it pins the Python version, owns the
  project environment and the lockfile; the system Python is not used). It pulls every source,
  writes one self-contained HTML file with charts (Chart.js inside the HTML) and opens it in the
  browser.
- The same HTML is printed to PDF with headless Chrome (`chrome --headless --print-to-pdf`) and
  emailed to the author through the Gmail API. Email clients strip JavaScript and SVG, which is why
  the email carries a PDF and not the HTML.
- Runs every Monday morning on the author's **PC** through Windows Task Scheduler, with "run task
  as soon as possible after a scheduled start is missed" so it catches up at the next logon. It can
  also be run by hand any time.
- The author cares how it looks. The HTML design is decided on a throwaway prototype first, so the
  layout is picked on real output, not described in prose.
- Every number shows its change against the previous week.

## Hard constraints

- **Public repo, private files local.** The repo is public on GitHub
  (`MantasDemenius/analytics-dashboard`). Code, HTML template and docs are public. Everything
  private lives inside the local repo but gitignored: `config/` (the real config, service account
  keys, the OAuth client file, saved refresh token and the app notes), `history/` (weekly numbers,
  including earnings), `out/` (generated HTML and PDF reports, which carry feedback text and users'
  emails). A `config.example.toml` with placeholder values is what gets committed. GitHub secret
  scanning and push protection are on by default for public repos and are a safety net, not the
  plan.
- **Nothing app-specific in the repo**, docs included: no app names, package names, Firebase
  project IDs, AdMob app, publisher or ad unit IDs, or paths into the apps' own repos. Most of these
  are technically public (they ship in the APK), but the author does not want them published. Code,
  tests and docs stay generic; `config.example.toml` and test fixtures use made-up values.
- **Free.** No paid service, no billing account turned on, no Claude tokens on the weekly path.
- **Text is never stored.** Review text and feedback text are fetched fresh each run and never
  written to the history folder. The apps promise users their feedback can be deleted on request;
  a stored copy would break that promise.
- **History is numbers only**, one snapshot per week, in the gitignored `history/` folder on the
  PC. It is what makes trends (earnings growth, installs growth) possible past each API's own
  window.
- **Config is a list of apps from day one**, even though only one app exists. When a second app
  arrives it gets its own section in the same weekly email (one email, not one per app). Build only
  for one app until then.
- New packages are a joint decision with the author. Agreed so far: `google-api-python-client`
  (Play reviews and reporting, AdMob, Gmail), `google-auth-oauthlib` (the one time login as the
  author), `google-cloud-storage` (Play report bucket), `google-cloud-firestore` (feedback) and
  `jinja2` (HTML template); `pytest` and `ruff` for development only. Deferred until needed:
  `google-cloud-bigquery` (only if Crashlytics comes from the BigQuery export) and
  `google-analytics-data` (phase 2). Not added directly: `requests` (the Google clients pull it in
  anyway), `pandas`, chart libraries.
- **Config is TOML**, read with the standard library's `tomllib`, so it needs no package.

## Phasing

1. **Phase 1:** Play, Crashlytics, Firestore feedback and AdMob. All of it works today with no app
   release.
2. **Phase 2:** the Analytics section, after the first app ships `firebase_analytics`. That is its
   own effort in the app's repo, and its data only starts from the release that adds it.

## Metrics, and where each comes from

| Section | Metrics | Source (as researched, see "Unverified" below) |
|---|---|---|
| Play: growth | new installs, uninstalls, net growth | Play Console's Cloud Storage report bucket (daily updated monthly CSVs). No API exposes these |
| Play: listing | store listing visitors and install conversion % | Same bucket |
| Play: ratings | average rating, and the **full text of every new review, all star levels** | Reviews API (`androidpublisher` reviews, last 7 days only) with the bucket's reviews CSV as backup for missed weeks |
| Play: vitals | crash rate and ANR rate against Play's bad behaviour threshold | Play Developer Reporting API |
| Crashlytics | crash free users %, **every issue** (not a top N), new and regressed issues called out | BigQuery sandbox export, or the API the Firebase MCP server uses. Not decided |
| Feedback | count and **full text of every new report**, both kinds (bug and feedback) | The app's Firestore feedback collection, read with a service account (client rules allow no reads) |
| AdMob | how the ads are doing: earnings, impressions, eCPM, **per ad unit**, plus earnings growth over time | AdMob API. Needs a one time OAuth login as the author; AdMob does not accept service accounts |
| Analytics (phase 2) | weekly and monthly active users, day 1 and day 7 retention, sessions per user, feature usage, first session funnel (open app to the app's first core action) | GA4 Data API |

Not wanted: % of users on the latest version.

## Credentials (one time, by the author)

- Play: grant the service account access to the reports bucket and the Reporting API. This project
  keeps its own copy of the key in `config/`; it never reads the apps' repos.
- Firebase: a service account that can read Firestore and the Crashlytics source.
- AdMob and Gmail: one OAuth consent as the author covering AdMob read and `gmail.send`.
- GA4 (phase 2): add the service account as a viewer on the property.

## Outside this project

Urgent problems are not this tool's job. Crashlytics' own new, regressed and trending issue emails
and Play Console's vitals threshold emails cover them; turning those on is a ticket in each app's
repo. This tool sends no alerts of its own.

## Rejected, and why

- **Firebase console as the hub** (linking AdMob and Play to Firebase): Play reviews, ratings and
  vitals still stay in Play Console, so it is never one place.
- **Looker Studio over BigQuery:** the only real live dashboard, but long history needs billing on
  (sandbox tables expire after 60 days), Play and AdMob have no native connectors, and feedback text
  has no connector at all. Rejected for the "free" constraint.
- **Paid aggregators** (Appfigures, AppFollow and similar): monthly fee, weak on Crashlytics and
  Firestore.
- **A weekly Claude routine publishing a claude.ai artifact:** pretty and could interpret, but costs
  Claude budget every week (reading a 30 to 60 KB report is roughly a short chat), needs Google
  credentials in a cloud agent, and drifts run to run. Kept only as an on demand extra: the author
  can ask Claude to publish a given week's HTML when they want it on their phone interactively.
- **A GitHub issue per week:** cannot show charts.
- **Living inside the first app's repo:** the author wants it for later apps too.
- **Dart** (the first choice, dropped the same day): the author knows it and `dart compile exe`
  gives Task Scheduler one native binary, but the work is mostly Google API glue, CSV parsing and
  HTML templating, where Python is stronger. Google ships first-party Python clients for Firestore,
  Cloud Storage, BigQuery and GA4 (Dart's `googleapis` is generated REST, and Firestore comes back
  as hand-unwrapped typed values); Dart has no built-in CSV parser or UTF-16 decoder for Play's
  report files; Jinja2 is a mature template engine with no settled Dart equivalent.

## Unverified, check before the spec rests on it

1. Crashlytics source: does the BigQuery sandbox export (free, daily batch, 60 day table expiry)
   work for this project, or is the API the Firebase MCP server calls usable from a script? Which
   gives every issue with users affected, new and regressed?
2. Play bucket: can the existing service account be granted read access to the reports bucket, and
   which CSVs carry installs, uninstalls, ratings, store listing conversion and reviews? Are they
   UTF-16 encoded?
3. Reviews API: is its 7 day window enough with a weekly run, or is the bucket's reviews CSV needed
   as the primary source?
4. AdMob API: does a network report break earnings down per ad unit per day as expected?
5. Headless Chrome PDF: do Chart.js charts render before the PDF is printed (may need
   `--virtual-time-budget` or rendering charts without animation)?

## Open questions for the spec

- The emailed PDF puts feedback text, and any email address a bug report carries, into the
  author's Gmail inbox, which is a copy outside Firestore. Does the PDF carry full feedback text,
  or counts plus text with emails and App IDs left out, while the local HTML shows everything?
