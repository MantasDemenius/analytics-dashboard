# Decisions so far

Outcome of a grilling session held on 2026-10-27, before this project had any code, and later
changes made in this repo (the language moved from Dart to Python on the same day), plus the phase 1
grilling session of 2026-11-03 ("Phase 1 design" below). Nothing here is specced yet. The
unverified facts at the bottom are GitHub tickets, and everything else still to be specced is on
the pinned Roadmap issue.

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
  also be run by hand any time, for any date range.
- The author cares how it looks. The HTML design is decided on a throwaway prototype first, so the
  layout is picked on real output, not described in prose.
- Every number shows its change against the previous period of the same length.

## Hard constraints

- **Public repo, private files local.** The repo is public on GitHub
  (`MantasDemenius/analytics-dashboard`). Code, HTML template and docs are public. Everything
  private lives inside the local repo but gitignored: `config/` (the real config, service account
  keys, the OAuth client file, saved refresh token and the app notes), `out/` (the latest
  generated HTML and PDF report, which carry feedback text and users' emails) and `logs/`. A `config.example.toml` with placeholder values is what gets committed. GitHub secret
  scanning and push protection are on by default for public repos and are a safety net, not the
  plan.
- **Nothing app-specific in the repo**, docs included: no app names, package names, Firebase
  project IDs, AdMob app, publisher or ad unit IDs, or paths into the apps' own repos. Most of these
  are technically public (they ship in the APK), but the author does not want them published. Code,
  tests and docs stay generic; `config.example.toml` and test fixtures use made-up values.
- **Free.** No paid service, no billing account turned on, no Claude tokens on the weekly path.
- **Text is never stored.** Review text and feedback text are fetched fresh each run and live only
  in the one latest report in `out/`, overwritten every run. The apps promise users their feedback
  can be deleted on request; a stored copy would break that promise.
- **No history in phase 1** (2026-11-03): every number and trend is recomputed from the sources on
  each run, since every chart fits inside the sources' own windows. If history is ever added (for
  trends past Crashlytics' 90 days), it holds numbers only.
- **Read only credentials.** Every key, role and scope this tool holds only reads. Two exceptions,
  both agreed with the author on 2026-10-30: `gmail.send`, because the report has to be emailed (it
  can send mail but not read the inbox), and Play Console's "Reply to reviews", because the Reviews
  API refuses service accounts without it. Never the publishing key an app uses for releases.
- **One config file per app** (agreed 2026-10-30): `config/apps/<app>.toml` names that app's
  Firebase project and app ID, package, Play report bucket, feedback collection and its own
  service account key (`config/apps/<app>-service-account.json`). Each app's service account lives
  in that app's own Firebase project, so no extra Cloud project exists. AdMob and Gmail belong to
  the author's Google accounts, not to an app, so every app shares two sign-ins through one OAuth
  client (`config/oauth-client.json`): `config/admob-token.json` (`admob.report` only) and
  `config/gmail-token.json` (`gmail.send` only), and `config/report.toml` holds the
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

| Section | Metrics | Source |
|---|---|---|
| Play: growth | new installs, uninstalls, net growth | Play Console's Cloud Storage report bucket (daily updated monthly CSVs), the installs overview file. No API exposes these. See "Play report bucket" below |
| Play: listing | store listing visitors and install conversion % | Same bucket, the store performance file |
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
  month. The docs say 3 to 7 days late, but on the real bucket it held a review from the day
  before. Dates are ISO 8601 UTC. Review text has its line breaks stripped (per the docs). A week
  can straddle two monthly files. File layout, encoding and the merge key are under "Play report
  bucket" below.
- **Store rating:** neither reviews source can give it, because star-only ratings are missing
  from the API and averaging only text reviews would skew it. It comes from the bucket's ratings
  overview CSV, which lags about 7 days and has glitches (see "Play report bucket").
- **New ratings in a range:** the reviews CSV carries every rating, star-only ones included, so
  the average of a range's new ratings is computed from its "Star Rating" column. Checked on
  2026-11-03: Play Console's "Average rating (last 28 days)" read 3.667, exactly the reviews CSV's
  last 28 days (one 1 star and two 5 star ratings).

Decision: review text comes from the Reviews API, which has no posting lag, merged by review with
the reviews CSV, which covers the days the API window has already dropped when a run is late. A
review written 8 days before a run is gone from the API unless edited, but should be in the CSV by
then. When a run is so late that neither source can be trusted for the whole week, the report says
so. The store rating comes from the ratings CSV.

## Play report bucket

Mapped on 2026-10-31 by reading the first app's bucket with its report service account (holding
only the read only Play permission). The bucket name lives in the app's config, never here.

- **Files:** monthly CSVs named `<prefix>_<package>_<YYYYMM>_<dimension>.csv`. The report reads
  three families, each from its `overview` (or `country`) file:
  - `stats/installs/installs_<package>_<YYYYMM>_overview.csv`
  - `stats/store_performance/store_performance_<package>_<YYYYMM>_country.csv`
  - `stats/ratings/ratings_<package>_<YYYYMM>_overview.csv` (the overview file does exist, though
    the help article lists only per-dimension ones)
  - and `reviews/reviews_<package>_<YYYYMM>.csv`, which has no dimension.

  Per-dimension files (app version, carrier, country, device, language, OS version, traffic
  source) exist too and are not needed. `stats/crashes/` stopped in 2024-11 and
  `total_store_performance` in 2026-08; neither is used (vitals come from the Reporting API).
- **Encoding:** every file is UTF-16LE with a byte order mark (`FF FE`), served with
  `text/csv; charset=utf-16le`. Python reads them with `bytes.decode("utf-16")` and the standard
  `csv` module; no package needed.
- **Dates:** stats files carry one row per day as `YYYY-MM-DD` in a `Date` column; the docs do not
  name a time zone. Reviews carry ISO 8601 UTC (`2026-10-19T12:35:08Z`) plus epoch milliseconds.
  **Days can be missing**: a day with no data has no row (the ratings file skipped 3 of 23 days in
  October), so the report treats a missing day as zero for counts and carries the last value for
  the rating.
- **Installs overview columns:** `Date`, `Package name`, `Daily Device Installs`, `Daily Device
  Uninstalls`, `Daily Device Upgrades`, `Total User Installs`, `Daily User Installs`, `Daily User
  Uninstalls`, `Active Device Installs`, `Install events`, `Update events`, `Uninstall events`.
  `Daily Device Uninstalls`, `Daily Device Upgrades` and `Total User Installs` are zero in every
  month back to 2024-02, so they are dead. Google publishes no definition of the rest. The report
  uses **`Daily User Installs` and `Daily User Uninstalls`**: the only live pair counted at the
  same level (users), so net growth is their difference. `Daily Device Installs` would pair with
  no live uninstall column, and the event columns count reinstalls.
- **Store performance columns:** `Date`, `Package name`, `Country / region`, `Store listing
  acquisitions`, `Store listing visitors`, `Store listing conversion rate`. Per the help article,
  visitors and acquisitions count only users who had the app on no device. A small app gets one
  `Other` row per day; a bigger one gets a row per country, so the report sums rows per day. The
  rate column carries noise in its last digits, so weekly conversion is summed acquisitions over
  summed visitors, never an average of the daily rates.
- **Ratings overview columns:** `Date`, `Package Name`, `Daily Average Rating` (0.0 on a day with
  no ratings), `Total Average Rating`. In October the total fits a lifetime average (3.7727 is
  83 / 22, and 3.6521 is 84 / 23 after one 1 star rating), but single rows jump to 1.0 or 0.0 and
  September wandered between 2.5 and 4.0 in a way no lifetime average could. A lifetime average
  rebuilt from every reviews CSV does not match it either (3.80 to 3.89 over the same days), so it
  cannot stand in. On 2026-11-03 Play Console showed a "Default Google Play rating" of 3.750 (24
  users), which no export carries; the total appears to follow it with the file's 7 day lag
  (see "Unverified" below).
- **Reviews CSV columns:** `Package Name`, `App Version Code`, `App Version Name`, `Reviewer
  Language`, `Device`, `Review Submit Date and Time`, `Review Submit Millis Since Epoch`, `Review
  Last Update Date and Time`, `Review Last Update Millis Since Epoch`, `Star Rating`, `Review
  Title`, `Review Text`, `Developer Reply Date and Time`, `Developer Reply Millis Since Epoch`,
  `Developer Reply Text`, `Review Link`. **Star-only ratings are rows** with empty text and an
  empty `Review Link`.
- **Merge key:** the `reviewId` query parameter of `Review Link` (a UUID) equals the Reviews API's
  `reviewId`, and `Review Last Update Millis Since Epoch` equals the API's
  `userComment.lastModified` to the millisecond; checked on a review present in both. Star-only
  rows have no id, but the API never returns them, so nothing needs merging for them. `Review Link`
  also carries the Play Console developer and app ids, so the report never prints the link.
- **Posting lag**, measured on files updated 2026-10-30: reviews held a review from 10-29, the
  installs overview ran to 10-26 (4 days), store performance to 10-24 (6 days), ratings to 10-23
  (7 days). So a Monday run cannot have the week that just ended from the bucket; see the open
  questions.

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
  that holds Gmail scopes. Publishing needs a home page and privacy policy link on the Branding
  page: the repo and its `PRIVACY.md`, with `github.com` as the authorized domain.
- **Two sign-ins, one scope each** (2026-10-30): `google_login.py admob` signs in as the account
  that owns AdMob, `google_login.py gmail` as the account the report is sent from. They may be
  different accounts, and a leaked AdMob token cannot send mail. Inviting the sending account to
  AdMob as a Reporter was tried and failed: AdMob refused the email as "already associated with an
  AdSense account", since a Google account can belong to only one AdSense or AdMob account.
- GA4 (phase 2): add the service account as a viewer on the property.

## AdMob report

Confirmed on 2026-10-30 with one real `accounts.networkReport:generate` call (AdMob API `v1`,
scope `admob.report`), for the last 7 days:

- **Dimensions** `DATE`, `AD_UNIT`, `FORMAT` give one row per ad unit per day. `AD_UNIT` carries
  the unit's ID as `value` and its name as `displayLabel`, so the report needs no unit list (which
  `admob.report` cannot read anyway: listing apps and ad units is refused).
- **Metrics** `ESTIMATED_EARNINGS` (`microsValue`, millionths of the account currency),
  `IMPRESSIONS`, `AD_REQUESTS`, `CLICKS` (`integerValue`), `IMPRESSION_RPM` (eCPM) and
  `MATCH_RATE` (`doubleValue`). The header's `localizationSettings.currencyCode` gives the
  currency; the report shows it rather than assuming one.
- **Days with no traffic have no row**: 7 days by 2 units came back as 9 rows. The report fills
  missing unit days with zero.
- **Earnings growth over time needs no history of our own:** grouped by `MONTH`, the API returned
  27 months back.

## Report layout

Picked by the author on 2026-10-30 from three rendered prototypes: **the dashboard layout**. It
reads fastest, which is what a weekly glance needs.

- Top: week range, generated time, and an "at a glance" table with one row per app (net growth,
  store rating, crash free users, crash rate, new feedback, ad earnings, each with its change).
- Per app: eight number cards with a 12 week sparkline each (installs, uninstalls, net growth,
  listing conversion, store rating, crash free users, Play crash rate, ad earnings), then cards
  per section: daily installs and uninstalls, a 12 week trend, vitals bars against Play's bad
  behaviour thresholds with last week's tick, rating breakdown with every review, a table of every
  Crashlytics issue (new and regressed first), feedback cards, and AdMob per ad unit with stacked
  12 week earnings.
- Every number shows its change against last week with an arrow, coloured by better or worse
  (a rise in uninstalls, crash rate, ANR rate or bug reports is worse).
- In the PDF each app starts on a new page; about 5 A4 pages per app.
- Rejected: a one column "newsletter" (nicest for long text, but longest and hardest to compare)
  and a dense "ledger" of tables (most compact, least friendly). Known weakness of the pick:
  review and feedback text is squeezed into two columns, so the build may give those a full width.

The prototype (`out/prototype/`, gitignored, made-up data) stays on the author's PC as the visual
reference until the real template replaces it, then gets deleted.

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

## Phase 1 design

Grilled with the author on 2026-11-03. Sources lag differently: reviews, feedback, Crashlytics
and AdMob are current to yesterday, Play vitals about 3 days behind (its API reports a freshness
date), the bucket 4 to 7 days.

**Running it**

- `uv run weekly-report [--from YYYY-MM-DD --to YYYY-MM-DD] [--email]`, dates inclusive. Every run
  builds the HTML and opens it. `--email` also prints the PDF and sends it; the scheduled task
  passes `--email`, so a run by hand never mails by accident. The run keeps no state, so it cannot
  know whether it already sent.
- **With no dates:** periods are Monday to Sunday. Fast sources report the week that just ended;
  each lagging source reports its newest Monday to Sunday week that is complete in its data
  (normally the week before), and each section header shows its own range. So the scheduled run
  always carries complete numbers, and if a lag shrinks the report catches up by itself.
- **With dates:** one range for every section, and each source gives what it has: missing days
  show "data to <date>", a source whose window does not reach shows "not available for this
  range" (Crashlytics reaches back 90 days, the Reviews API 7, so older reviews come from the CSV
  only).
- **Comparisons:** every change is against the period of the same length just before. Where a
  source has only part of the range, the previous period is cut to the same days, so 3 days are
  never set against 7. Sparklines and trend charts show 12 periods of the range's length.
  Levels (store rating, vitals) show the value at the end of the range.
- **Days** are each source's own: Pacific Time for vitals and AdMob (their only supported zone),
  UTC for Crashlytics, undocumented (likely Pacific) for the bucket. No conversion.
- `scripts/schedule_task.ps1` registers the Task Scheduler task: Monday 08:00, only when the author
  is logged on, catch up after a missed start, `--email`, output to the gitignored `logs/`.
  Running it again replaces the task.

**Section rules**

- Installs: `Daily User Installs` and `Daily User Uninstalls` (see "Play report bucket").
- Store rating card: `Total Average Rating`, labelled "Google Play rating, as of <date>", taking
  the most common value in the file's last 7 non-zero rows to ride over glitches. If the check
  under "Unverified" fails, the card falls back to the 28 day average computed from the reviews
  CSV. The ratings section always shows the range's new ratings (average and count).
- Reviews: Reviews API requested with `translationLanguage` English; a translated review shows the
  translation in `text` with `originalText` below in smaller type. A review only in the CSV shows
  its original with a language tag. A review the CSV already holds is labelled new or edited by
  its submit date; one only the API has is labelled "new or edited". Review ids are not
  remembered. A review card marks "replied"; the reply text is in the HTML only.
- Vitals: user-perceived crash and ANR rate, 28 day user weighted
  (`userPerceivedCrashRate28dUserWeighted`, `userPerceivedAnrRate28dUserWeighted`), labelled "28
  days", against Play's bad behaviour thresholds of 1.09% and 0.47%. Google's API docs do not tie a
  metric to the threshold in words; Play judges on a 28 day average, which this is. The change is
  against the value one period earlier; the sparkline samples it per period.
- Crashlytics: every issue, new and regressed first, then by users affected, events breaking ties.
- Feedback: reports whose `createdAt` falls in the range, as cards (kind, stars, liked items, app
  and Android version, message, error), plus the current count of reports not yet `handled`. The
  tool only reads and never sets `handled`.
- AdMob: as under "AdMob report".

**Output and failure**

- `out/` keeps only the latest report, overwritten every run; the author's inbox keeps the PDFs.
- The emailed PDF carries feedback text but never a bug report's `email` or `appId`; the local HTML
  shows everything. The app's deletion procedure gains a step to search Gmail for report emails
  quoting the user (a ticket in the app's repo).
- Email subject "Weekly app report, <range>"; the body is the at-a-glance table as plain text, with
  the PDF attached.
- A source that fails (expired token, outage, missing files) does not stop the report: its section
  shows the error, a problems box at the top lists every failure, and the run exits non-zero. If
  Gmail fails or Chrome prints a blank PDF, the run logs to `logs/` and exits non-zero. No other
  alerts.
- Chrome is found at its standard install paths, with an optional override in `config/report.toml`.

**Code**

```
src/weekly_report/
  __main__.py        command line, runs everything
  config.py          reads config/apps/*.toml and config/report.toml
  periods.py         picks each source's period
  model.py           plain dataclasses: Metric(value, previous, series), sections, AppReport
  sources/           play_bucket.py, play_api.py, crashlytics.py, feedback.py, admob.py
  render.py          Jinja2 template to one HTML file, Chart.js inlined
  pdf.py             headless Chrome, then a page count check
  mail.py            Gmail send
  templates/report.html.j2
  vendor/chart.umd.min.js   Chart.js 4.4.1, MIT, vendored (agreed 2026-11-03)
```

- Each source splits into a thin `fetch` (network calls only) and pure parse and summarise
  functions (bytes or dicts in, dataclasses out). Tests cover the pure functions with made-up
  fixtures and never call Google; `scripts/smoke_check.py` and real runs prove `fetch`.
- The code loops over every app config but is built and tested with one app. How a second app
  with less data shows is left until one joins.
- First slice (tracer bullet): Play new installs for the default period, from config through
  HTML, PDF and email. It proves UTF-16 parsing, the lag aware period picker and the comparison
  first; every other section is its own ticket on top.

**Running it remotely**

- From the phone through Remote Control into any Claude session open on the PC, whatever project
  it is in. The PC is always on, and the keys never leave it.
- A global skill in the author's Claude config folder (not committed, since it holds a local
  path), `/run-report [from] [to]`, runs `uv run --directory <repo> weekly-report --email
  --no-open` with the dates given or the default period. `--no-open` keeps an unattended PC from
  showing the report on screen. The repo's README documents what it runs.
- **The command line never prints review or feedback text**, only the period, counts, the
  problems list and where the files went. The skill passes on only that and never opens the
  report files, so no user-written text reaches a Claude transcript. The author reads the report,
  feedback included, in the emailed PDF.
- A remote run costs a few thousand Claude tokens; the weekly run stays on Task Scheduler with
  none.
- It is the last phase 1 ticket, after email works. Its acceptance includes one real run from the
  phone in a session for another project, which settles what Claude Code's docs leave open
  (whether a skill can be invoked over Remote Control).

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
  credentials in a cloud agent, and drifts run to run. An on demand artifact was then offered
  and declined on 2026-11-03: Claude must read a page to publish it, so a full report would put
  feedback text in a transcript, and a numbers only one leaves out the feedback the author mostly
  cares about. Email is the remote path.
- **Running remotely from a Claude cloud session** (2026-11-03): it would work with the PC off,
  but the service account key and both OAuth tokens would sit in the cloud environment's plain
  environment variables, which Claude Code's docs warn against for secrets (its network secrets
  only attach header keys, and Google's keys must be exchanged by the tool itself), and report
  text would be built next to an agent holding `gmail.send`. A cloud session also cannot reach
  the PC. The one workable bridge, a PC task polling GitHub for a trigger from the author's
  account, is kept as an option if Remote Control proves annoying: it costs a poller, `gh`
  signed in on the PC, an author-only filter and a public trace unless a private repo is used.
- **Crashlytics BigQuery export** (sandbox, as the Crashlytics source): free, but the export has
  no issue signals or state, so new and regressed issues cannot be told apart once its 60 day
  tables expire. It also needs a console link by the author, the sessions export for crash free
  users, a daily batch lag, and `google-cloud-bigquery`. Kept only as the fallback named under
  "Crashlytics source".
- **A GitHub issue per week:** cannot show charts.
- **A weekly history snapshot** (planned until 2026-11-03): every chart fits in the sources' own
  windows, so it only added state, an empty first run and a gap after a missed week.
- **Mocking the Google clients in tests:** such tests mostly test the mocks.
- **Chart.js from a CDN:** printing would depend on the network and its timing.
- **Living inside the first app's repo:** the author wants it for later apps too.
- **Dart** (the first choice, dropped the same day): the author knows it and `dart compile exe`
  gives Task Scheduler one native binary, but the work is mostly Google API glue, CSV parsing and
  HTML templating, where Python is stronger. Google ships first-party Python clients for Firestore,
  Cloud Storage, BigQuery and GA4 (Dart's `googleapis` is generated REST, and Firestore comes back
  as hand-unwrapped typed values); Dart has no built-in CSV parser or UTF-16 decoder for Play's
  report files; Jinja2 is a mature template engine with no settled Dart equivalent.

## Unverified, check before the spec rests on it

1. Does the ratings CSV's `Total Average Rating` equal Play Console's "Default Google Play
   rating"? On 2026-11-03 Console showed 3.750; once the file's rows for late October post, its
   total should read the same. If not, the store rating card uses the fallback under "Phase 1
   design".

## Open questions for the spec

None open. Phase 1 is grilled; the spec is next.
