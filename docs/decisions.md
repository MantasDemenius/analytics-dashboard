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
- **Read only credentials.** Every key, role and scope this tool holds only reads. Two exceptions,
  both agreed with the author on 2026-10-30: `gmail.send`, because the report has to be emailed (it
  can send mail but not read the inbox), and Play Console's "Reply to reviews", because the Reviews
  API refuses service accounts without it. Never the publishing key an app uses for releases.
- **One config file per app** (agreed 2026-10-30): `config/apps/<app>.toml` names that app's
  Firebase project and app ID, package, Play report bucket, feedback collection and its own
  service account key (`config/apps/<app>-service-account.json`). Each app's service account lives
  in that app's own Firebase project, so no extra Cloud project exists. AdMob and Gmail belong to
  the author's Google account, not to an app, so they share one sign-in
  (`config/oauth-client.json`, `config/oauth-token.json`) and `config/report.toml` holds the
  recipient. One run covers every app config, all in one weekly email with a section per app.
  `scripts/setup_app.sh <app>` creates all of it, and `scripts/smoke_check.py <app>` proves it.
  Build only for one app until a second arrives.
- New packages are a joint decision with the author. Agreed so far: `google-api-python-client`
  (Play reviews and reporting, AdMob, Gmail), `google-auth-oauthlib` (the one time login as the
  author), `google-cloud-storage` (Play report bucket), `google-cloud-firestore` (feedback) and
  `jinja2` (HTML template); `pytest` and `ruff` for development only. Deferred until needed:
  `google-cloud-bigquery` (only if the Crashlytics API turns out unreadable with a service
  account and the BigQuery export becomes the fallback) and
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
| Play: ratings | average rating, and the **full text of every new review, all star levels** | Review text: Reviews API first, merged with the bucket's reviews CSV. Average rating: the bucket's ratings CSV. See "Play reviews and rating source" below |
| Play: vitals | crash rate and ANR rate against Play's bad behaviour threshold | Play Developer Reporting API |
| Crashlytics | crash free users %, **every issue** (not a top N), new and regressed issues called out | Crashlytics REST API (`firebasecrashlytics` `v1alpha`), read with a service account. See "Crashlytics source" below |
| Feedback | count and **full text of every new report**, both kinds (bug and feedback) | The app's Firestore feedback collection, read with a service account (client rules allow no reads) |
| AdMob | how the ads are doing: earnings, impressions, eCPM, **per ad unit**, plus earnings growth over time | AdMob API. Needs a one time OAuth login as the author; AdMob does not accept service accounts |
| Analytics (phase 2) | weekly and monthly active users, day 1 and day 7 retention, sessions per user, feature usage, first session funnel (open app to the app's first core action) | GA4 Data API |

Not wanted: % of users on the latest version.

## Crashlytics source

Settled on 2026-10-30: the Crashlytics REST API at `firebasecrashlytics.googleapis.com`, version
`v1alpha`, the same API the Firebase MCP server calls. It is documented publicly under Firebase's
`reference/crashlytics/rest`, and Firebase states that fetching Crashlytics data from it costs
nothing.

- **Every issue:** the `topIssues` report (`projects/{project}/apps/{app_id}/reports/topIssues`)
  returns one group per issue and pages with `pageSize`, `nextPageToken` and `totalSize`, so the
  report reads every page rather than a top N. Its `interval` filter accepts anything from 90 days
  ago to now and defaults to the last 7 days.
- **Users affected:** each group's metrics carry `eventsCount` and `impactedUsersCount`.
- **New and regressed:** each issue carries `signals` set by Crashlytics (`SIGNAL_FRESH` for newly
  detected, `SIGNAL_REGRESSED` for closed issues seen again), plus `firstSeenTime`,
  `firstSeenVersion` and `state`. The report can also filter by signal.
- **Crash free users:** the metrics carry `crashFreeUsersPercentage`.
- **From a script:** OAuth scope `cloud-platform` or `firebase`. A service account needs the
  Firebase Crashlytics Viewer role (`roles/firebasecrashlytics.viewer`), and the Firebase
  Crashlytics API must be enabled on the project. No console linking is needed.
- **No new package:** `google-api-python-client` builds the client from the public discovery
  document (`https://firebasecrashlytics.googleapis.com/$discovery/rest?version=v1alpha`).

Proven on 2026-10-30 by `scripts/smoke_check.py`: a service account holding only the viewer role
reads the `topIssues` report. The BigQuery export stays the fallback if that ever stops working.

Risk accepted: `v1alpha` has no deprecation promise. The report uses one call, so a change costs
little to follow.

## Play reviews and rating source

Settled on 2026-10-30 from Google's docs (`developers.google.com/android-publisher/reply-to-reviews`,
the `reviews` REST reference, and Play Console help article 6135870 on monthly report exports).

- **Reviews API window:** it returns only reviews "created or modified within the last week". The
  docs do not define the edge (7 days rolling is assumed). It returns **only reviews with text**;
  star-only ratings never come from it. Pages hold up to 100 reviews (`maxResults`, `token`); the
  quota is 200 reads per hour per app.
- **Edited reviews:** an edit puts a review back inside the window. The API returns only the latest
  text and stars, and its one user timestamp, `userComment.lastModified`, cannot tell an edit from
  a new review. The reviews CSV can: it has both "Review Submit Date and Time" and "Review Last
  Update Date and Time".
- **Developer replies:** replied reviews are still returned; the user comment is `comments[0]` and
  the reply `comments[1]`, each with its own `lastModified`. Always read the user comment's time.
- **Reviews CSV:** `reviews/reviews_<package>_<YYYYMM>.csv` in the report bucket, one file per
  month, captured daily but **posted 3 to 7 days late**. Dates are ISO 8601 UTC. Review text has
  its line breaks stripped. Docs imply UTF-16 (they say to convert it to UTF-8 for BigQuery). A
  week can straddle two monthly files.
- **Average rating:** neither reviews source can give it, because star-only ratings are missing
  from the API and averaging only text reviews would skew it. It comes from the bucket's ratings
  CSV (`stats/ratings/ratings_<package>_<YYYYMM>_<dimension>.csv`, columns "Daily Average Rating"
  and "Total Average Rating"), which has the same 3 to 7 day lag.

Decision: review text comes from the Reviews API, which has no posting lag, merged by review with
the reviews CSV, which covers the days the API window has already dropped when a run is late. A
review written 8 days before a run is gone from the API unless edited, but should be in the CSV by
then. When a run is so late that neither source can be trusted for the whole week, the report says
so. The average rating comes from the ratings CSV.

Left for the bucket mapping ticket to confirm on real files: whether an `overview` ratings file
exists (the help article lists only per-dimension files), whether the reviews CSV carries
star-only rows, the encoding, and how the review id is read from the CSV's "Review Link" column so
the two sources can be merged.

## Credentials (one time, by the author)

All of it is walked through by `scripts/setup_app.sh <app>`.

- Per app, a new service account `analytics-report` in the app's Firebase project, with the
  Cloud roles Cloud Datastore Viewer (`roles/datastore.viewer`) and Firebase Crashlytics Viewer
  (`roles/firebasecrashlytics.viewer`), and the Crashlytics, Play Developer Reporting, Play Android
  Developer, Firestore and Cloud Storage APIs enabled. It is not the publishing service account.
- Play Console invites that service account with the account wide permission "View app information
  and download bulk reports (read only)" (Play's help says bulk reports need it set globally) and,
  for the app only, "Reply to reviews". Access to the report bucket can take up to a day to start.
- AdMob and Gmail: one OAuth client (Desktop app) in the first app's project, with the scopes
  `admob.report` (the narrowest that reads reports) and `gmail.send`. Its consent screen must be
  **In production**: in Testing, Google expires refresh tokens after 7 days and the weekly run would
  fail. Unverified is fine for personal use. Changing the Google password also revokes a token
  that holds Gmail scopes.
- GA4 (phase 2): add the service account as a viewer on the property.

## Printing the PDF

Settled on 2026-10-30 by printing a test page of 8 Chart.js 4.4.1 charts (inlined, 3 A4 pages)
with Chrome 156 on the author's PC, 5 runs per variant, each checked on the rendered PDF.

- **Charts must not animate.** With Chart.js' default animation every run printed flat or
  half-drawn charts, and `--virtual-time-budget` did not fix it (one run came out blank). With
  `animation: false` (set `Chart.defaults.animation = false` before any chart is created) every
  run printed every chart fully, byte-identical run to run.
- **Chart size when printing:** Chart.js draws at the browser window's width and headless Chrome
  does not redraw on print. The 8 chart test page printed at the right size, but the fuller layout
  prototypes came out with charts clipped (x axis cut off) at Chrome's default window. What fixed
  it there: print with `--window-size=794,1123` (A4 at 96 dpi) plus a print-only CSS rule that
  scales each chart canvas to its box. Grid columns holding charts need `minmax(0, 1fr)`, or
  charts push them wider than the page. Never force canvas width and height in screen CSS: it
  makes Chart.js resize in a loop and Chrome hangs.
- **Command:** `chrome.exe --headless --disable-gpu --user-data-dir=<dedicated dir>
  --window-size=794,1123 --no-pdf-header-footer --print-to-pdf=<out.pdf> file:///<report.html>`. It exits in under a
  second and leaves no process behind.
- **`--no-pdf-header-footer` is required:** by default Chrome prints the date, title and the file's
  local path on every page, which would leak a private path into the emailed PDF.
- **A dedicated `--user-data-dir`:** without it Chrome may hand the job to the author's open
  browser session.
- **Page CSS:** Chrome defaults to US Letter, so the template sets `@page { size: A4; margin: 12mm }`,
  and `break-inside: avoid` on each section keeps a heading with its chart.
- **Exit code says nothing about the render:** Chrome returned 0 for blank PDFs too, so the run
  checks the output another way (page count or size), not the exit code.

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
- **Crashlytics BigQuery export** (sandbox, as the Crashlytics source): free, but the export has
  no issue signals or state, so new and regressed issues cannot be told apart once its 60 day
  tables expire. It also needs a console link by the author, the sessions export for crash free
  users, a daily batch lag, and `google-cloud-bigquery`. Kept only as the fallback named under
  "Crashlytics source".
- **A GitHub issue per week:** cannot show charts.
- **Living inside the first app's repo:** the author wants it for later apps too.
- **Dart** (the first choice, dropped the same day): the author knows it and `dart compile exe`
  gives Task Scheduler one native binary, but the work is mostly Google API glue, CSV parsing and
  HTML templating, where Python is stronger. Google ships first-party Python clients for Firestore,
  Cloud Storage, BigQuery and GA4 (Dart's `googleapis` is generated REST, and Firestore comes back
  as hand-unwrapped typed values); Dart has no built-in CSV parser or UTF-16 decoder for Play's
  report files; Jinja2 is a mature template engine with no settled Dart equivalent.

## Unverified, check before the spec rests on it

1. Play bucket: which CSVs carry installs, uninstalls, ratings, store listing conversion and
   reviews? Are they UTF-16 encoded?
2. AdMob API: does a network report break earnings down per ad unit per day as expected?

## Open questions for the spec

- The emailed PDF puts feedback text, and any email address a bug report carries, into the
  author's Gmail inbox, which is a copy outside Firestore. Does the PDF carry full feedback text,
  or counts plus text with emails and App IDs left out, while the local HTML shows everything?
- Should the report mark a review as "edited" rather than "new"? The CSV's submit date can tell
  them apart once it is posted; for the API's newest days the only way is remembering review ids
  already seen, and history is numbers only. Is a list of review ids allowed in history, or is
  "new or edited" one label?
