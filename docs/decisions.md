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
- **This week's new ratings:** the reviews CSV carries every rating, star-only ones included, so
  the average of the week's new ratings can be computed from its "Star Rating" column.

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
  cannot stand in. Which value the report shows as the store rating is an open question below.
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
  27 months back. The weekly snapshot is still kept for week over week changes.

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

None open.

## Open questions for the spec

- The emailed PDF puts feedback text, and any email address a bug report carries, into the
  author's Gmail inbox, which is a copy outside Firestore. Does the PDF carry full feedback text,
  or counts plus text with emails and App IDs left out, while the local HTML shows everything?
- Should the report mark a review as "edited" rather than "new"? The CSV's submit date tells them
  apart, and on the real bucket the reviews CSV was only a day behind, so only the newest day or
  so would lack it. Is that gap labelled "new or edited", or are review ids remembered in history
  (which is numbers only today)?
- Which "average rating" leads: the store rating, or the average of this week's new ratings? They
  tell different stories; the prototype shows both.
- Which week does a Monday run report? The bucket lags 4 to 7 days (installs, listing, ratings)
  while the APIs are current. Options: every section reports the week that just ended and bucket
  numbers show "data to <date>"; every section reports the week before it so all numbers cover
  the same complete days; or bucket sections report their own latest complete 7 days, labelled.
- Which value is the store rating, given the ratings CSV's glitches? The latest
  `Total Average Rating` can be 1.0 or 0.0 on a bad day. Compare it against the rating Play
  Console shows before picking a rule (for example, the most common value over the last 7 rows).
- Reviews not in English: show the original, the Reviews API's translation, or both?
- Crashlytics issue order: new and regressed first (as prototyped), or by users affected, or by
  events?
- When a second app lacks some history, do its rows show "n/a" or disappear?
- What the vitals figures mean: confirm whether the Reporting API's crash and ANR rates are 28 day
  rolling values or weekly ones before labelling them.
