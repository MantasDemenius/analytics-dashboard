"""Renders a full report from made-up data to out/sample/, as HTML and as the printed PDF.

Every section ticket adds its section here, so the layout can be checked by eye without real
data. Covers a rise, a fall and no change, a section with data ending inside its range, a failed
source and a range a source cannot reach. The reviews cover every label, a translation, a review
only the report holds, a reply, a run too late for part of the range and a week with no ratings.
The vitals cover rates under Play's bad behaviour thresholds, a crash rate above its threshold,
both rates above theirs with data ending inside the range, and a rate with no change.
Crashlytics covers new, regressed, early, repetitive and plain issues of every kind and state,
60 issues so the table runs over pages, a range with data ending inside it, a range at the 90
day limit with no comparison, and a range with no issues.
Feedback covers bug reports with and without an email, app ID, error and message, feedback with
and without a message and liked items, every star level, a rise and a fall in each kind, a long
list, a range with data ending inside it and a range with no reports. The email and app ID show
on screen and are left out of the PDF.

Run: uv run python scripts/render_sample.py
"""

import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from weekly_report import pdf
from weekly_report.model import (
    AppReport,
    Crashlytics,
    ErrorKind,
    Failure,
    Feedback,
    Growth,
    Issue,
    IssueState,
    Label,
    Listing,
    Metric,
    Point,
    Report,
    ReportKind,
    Review,
    Reviews,
    Signal,
    Unavailable,
    UserReport,
    Vitals,
)
from weekly_report.periods import TREND_PERIODS, Coverage, Period
from weekly_report.render import render, write
from weekly_report.sources.crashlytics import sorted_issues

OUT_DIR = Path("out/sample")
REPORT_WEEK = Period(date(2026, 10, 26), date(2026, 11, 1))
BUCKET_WEEK = REPORT_WEEK.previous()
LISTING_WEEK = BUCKET_WEEK.previous()
VITALS_WEEK = BUCKET_WEEK
CRASHLYTICS_WEEK = REPORT_WEEK
FEEDBACK_WEEK = REPORT_WEEK


def swinging(
    period: Period, base: float, slope: float, this_week: float
) -> dict[date, float]:
    """Made-up counts per day: a gentle trend with a slow swing, then `this_week` per day."""
    first = period.trailing(TREND_PERIODS)[0].start
    daily = {}
    for offset in range((period.start - first).days):
        day = first + timedelta(days=offset)
        swing = 1 + 0.12 * math.sin(offset / 9) + 0.2 * math.sin(offset * 2.1)
        daily[day] = round((base + slope * offset) * swing)
    for offset, day in enumerate(period.days()):
        daily[day] = round(this_week * (0.85 + 0.05 * offset))
    return daily


def growth(
    installs: dict[date, float],
    uninstalls: dict[date, float],
    data_to: date | None = None,
) -> Growth:
    coverage = Coverage(BUCKET_WEEK, data_to)
    net = {day: installs.get(day, 0) - uninstalls.get(day, 0) for day in installs}
    return Growth(
        coverage,
        installs=Metric.summed(installs, coverage),
        uninstalls=Metric.summed(uninstalls, coverage),
        net=Metric.summed(net, coverage),
    )


def listing(
    visitors: dict[date, float], rate: float, data_to: date | None = None
) -> Listing:
    coverage = Coverage(LISTING_WEEK, data_to)
    acquisitions = {day: round(count * rate) for day, count in visitors.items()}
    visited = Metric.summed(visitors, coverage)
    acquired = Metric.summed(acquisitions, coverage)
    return Listing(
        coverage,
        visitors=visited,
        acquisitions=acquired,
        conversion=Metric.ratio(acquired, visited),
    )


def vital(now: float, before: float, coverage: Coverage) -> Metric:
    """A made-up rate that swings through the weeks before and sits at `now` after them."""
    last_week = VITALS_WEEK.previous().end

    def level(day: date) -> float:
        if day > last_week:
            return now
        return before * (1 + 0.18 * math.sin((last_week - day).days / 9))

    return Metric.level(level, coverage)


def vitals_section(
    crash: tuple[float, float],
    anr: tuple[float, float],
    data_to: date | None = None,
) -> Vitals:
    coverage = Coverage(VITALS_WEEK, data_to)
    return Vitals(
        coverage,
        crash_rate=vital(*crash, coverage),
        anr_rate=vital(*anr, coverage),
    )


def rating_wave(day: date) -> float:
    return 3.7 + 0.3 * math.sin(day.toordinal() / 17)


def reviews_section(
    new_ratings: dict[date, float],
    average: float,
    cards: tuple[Review, ...] = (),
    breakdown: dict[int, int] | None = None,
    uncovered: tuple[Period, ...] = (),
) -> Reviews:
    coverage = Coverage(REPORT_WEEK)
    stars = {day: count * average for day, count in new_ratings.items()}
    count = Metric.summed(new_ratings, coverage)
    return Reviews(
        coverage,
        store_rating=Metric.level(rating_wave, coverage),
        new_ratings=count,
        new_average=Metric.ratio(Metric.summed(stars, coverage), count, per=1),
        breakdown=breakdown or {5: 0, 4: 0, 3: 0, 2: 0, 1: 0},
        reviews=cards,
        uncovered=uncovered,
    )


def card(
    stars: int,
    text: str,
    day: int,
    label: Label = Label.NEW,
    title: str = "",
    original_text: str | None = None,
    language: str | None = None,
    reply: str | None = None,
) -> Review:
    return Review(
        stars,
        title,
        text,
        original_text,
        language,
        label,
        datetime(2026, 10, day, 14, 30),
        reply,
    )


EXAMPLE_REVIEWS = (
    card(
        5,
        "Exactly what I needed. The widgets are quick and the dark theme is easy on the eyes.",
        31,
        title="Exactly what I needed",
        reply="Thank you, we are glad it helps. More widgets are on the way.",
    ),
    card(1, "Crashes every time I open it after the update.", 30, title="Broken"),
    card(
        4,
        "Was missing a search before, the new version fixed that. Still wish it synced between my devices.",
        30,
        Label.EDITED,
    ),
    card(
        5,
        "Very easy to use, the widgets are great.\nI use them every day.",
        29,
        Label.NEW_OR_EDITED,
        title="Great",
        original_text="Super\nSehr einfach zu bedienen, die Widgets sind toll.\nIch nutze sie jeden Tag.",
    ),
    card(
        3,
        "Bom, mas poderia ter mais opções.",
        28,
        language="pt",
        reply="Obrigado pelo comentário!",
    ),
    card(2, "", 27, title="Too many ads"),
    card(
        4,
        "A very long review without a single line break, written by someone who wanted to explain "
        "every detail of how they use the app on their commute, at home, at work and on holiday, "
        "including a complaint about the notification sound that cannot be changed. "
        * 2,
        26,
    ),
)


def crash_free_wave(now: float, period: Period) -> list[Point]:
    """Made-up crash free percents that swing through the weeks before and end at `now`."""
    weeks = period.trailing(TREND_PERIODS)
    return [
        Point(
            week.start,
            now if week == period else now - 0.8 + 1.2 * math.sin(index / 2.2) ** 2,
        )
        for index, week in enumerate(weeks)
    ]


def crashlytics_section(
    now: float,
    before: float,
    issues: tuple[Issue, ...],
    data_to: date | None = None,
    trend: int = TREND_PERIODS,
) -> Crashlytics:
    coverage = Coverage(CRASHLYTICS_WEEK, data_to)
    points = crash_free_wave(now, CRASHLYTICS_WEEK)[-trend:]
    return Crashlytics(
        coverage,
        crash_free=Metric(now, before, trend=tuple(points)),
        issues=issues,
    )


def issue(
    title: str,
    subtitle: str,
    users: int,
    events: int,
    signals: tuple[Signal, ...] = (),
    kind: ErrorKind = ErrorKind.FATAL,
    state: IssueState = IssueState.OPEN,
    version: str | None = "2.4.0",
) -> Issue:
    return Issue(
        title,
        subtitle,
        kind,
        state,
        signals,
        users,
        events,
        version,
        f"https://console.example/issues/{title.replace(' ', '-')}",
    )


EXAMPLE_ISSUES = (
    issue(
        "MainActivity.onResume",
        "java.lang.IllegalStateException: Fragment not attached",
        41,
        96,
        (Signal.FRESH,),
        version="2.5.0",
    ),
    issue(
        "WidgetProvider.update",
        "java.lang.NullPointerException: Attempt to invoke virtual method on a null object",
        7,
        12,
        (Signal.REGRESSED, Signal.REPETITIVE),
        version="2.1.0",
    ),
    issue("Database.query", "android.database.sqlite.SQLiteException", 120, 410),
    issue(
        "SyncWorker.doWork",
        "java.net.SocketTimeoutException",
        88,
        1034,
        (Signal.REPETITIVE,),
        ErrorKind.NON_FATAL,
    ),
    issue(
        "SettingsFragment.onCreate",
        "java.lang.ClassCastException",
        25,
        31,
        (Signal.EARLY,),
    ),
    issue(
        "Input dispatching timed out",
        "Waiting to send non-key event because the touched window has not finished",
        14,
        20,
        kind=ErrorKind.ANR,
    ),
    issue(
        "LegacyExporter.write",
        "java.io.IOException: No space left on device",
        3,
        3,
        kind=ErrorKind.NON_FATAL,
        state=IssueState.CLOSED,
        version=None,
    ),
    issue(
        "ThemeLoader.apply",
        "android.content.res.Resources$NotFoundException",
        2,
        2,
        state=IssueState.MUTED,
        version="2.0.1",
    ),
)
MANY_ISSUES = sorted_issues(
    [
        issue(
            f"com.example.feature{number}.Handler.run",
            "java.lang.RuntimeException: unexpected state "
            + "in the handler " * (number % 4),
            max(1, 60 - number),
            max(1, 140 - 2 * number),
            (Signal.FRESH,)
            if number == 3
            else (Signal.REGRESSED,)
            if number == 9
            else (),
            ErrorKind.NON_FATAL if number % 5 == 0 else ErrorKind.FATAL,
        )
        for number in range(60)
    ]
)


def feedback_section(
    reports: tuple[UserReport, ...],
    counts: tuple[int, int, int, int],
    unhandled: int,
    data_to: date | None = None,
) -> Feedback:
    """`counts` are the range's bug reports and feedback, then the same two a period earlier."""
    bugs, suggestions, bugs_before, suggestions_before = counts
    return Feedback(
        Coverage(FEEDBACK_WEEK, data_to),
        new=Metric(bugs + suggestions, bugs_before + suggestions_before),
        bugs=Metric(bugs, bugs_before),
        suggestions=Metric(suggestions, suggestions_before),
        unhandled=unhandled,
        reports=reports,
    )


def bug_report(
    day: int,
    message: str,
    android: str | None = "14",
    error: str | None = None,
    email: str | None = None,
    app_id: str | None = None,
    hour: int = 10,
) -> UserReport:
    return UserReport(
        ReportKind.BUG,
        datetime(2026, 10, day, hour, 5, tzinfo=UTC),
        "2.4.0",
        message,
        android,
        error,
        email,
        app_id,
        None,
        (),
    )


def feedback_report(
    day: int,
    stars: int,
    message: str,
    liked: tuple[str, ...] = (),
    version: str = "2.4.0",
    hour: int = 16,
) -> UserReport:
    return UserReport(
        ReportKind.FEEDBACK,
        datetime(2026, 10, day, hour, 40, tzinfo=UTC),
        version,
        message,
        None,
        None,
        None,
        None,
        stars,
        liked,
    )


EXAMPLE_FEEDBACK = (
    bug_report(
        31,
        "After importing a file the list stays empty and I cannot add anything new.\nI tried twice.",
        email="reader@example.com",
        app_id="a1b2c3d4e5f6",
        error="FormatException: unexpected end of input (at character 412)",
        hour=18,
    ),
    feedback_report(
        31,
        5,
        "Love it. A search across everything would make it perfect.",
        ("speed", "design", "ease"),
        hour=9,
    ),
    bug_report(30, "", error="Import failed: file is not valid", email="x@example.com"),
    feedback_report(30, 3, "", ("design",), version="2.3.1"),
    bug_report(
        29, "The back button closes the app instead of the screen.", android="13"
    ),
    feedback_report(29, 1, "Too many ads.", ()),
    bug_report(
        28,
        "Widgets stop updating after a day.",
        android=None,
        app_id="f6e5d4c3b2a1",
    ),
    feedback_report(28, 4, "", ()),
    feedback_report(
        27,
        2,
        "A very long message without a single line break, written by someone who wanted to "
        "describe every detail of how they use the app and what they would change, including "
        "the notification sound that cannot be changed. " * 3,
        ("content", "filters", "speed", "design", "ease"),
    ),
    bug_report(27, "Crash on start.", email="late@example.com", app_id="0a0b0c0d0e0f"),
)


def many_feedback() -> tuple[UserReport, ...]:
    """Reports on every day of the range, 30 in all, newest first."""
    reports = [
        feedback_report(
            26 + number % 5,
            1 + number % 5,
            f"Message number {number}, with a few words of opinion about the app.",
            ("speed",) if number % 3 == 0 else (),
            hour=8 + number % 12,
        )
        if number % 2
        else bug_report(
            26 + number % 5,
            f"Bug number {number}, something went wrong.",
            email=f"user{number}@example.com" if number % 4 == 0 else None,
            hour=8 + number % 12,
        )
        for number in range(30)
    ]
    return tuple(sorted(reports, key=lambda each: each.at, reverse=True))


def flat_week() -> dict[date, float]:
    daily = swinging(BUCKET_WEEK, base=30, slope=0.05, this_week=34)
    previous = BUCKET_WEEK.previous().days()
    total = sum(daily[day] for day in BUCKET_WEEK.days())
    for day in previous:
        daily[day] = 0
    daily[previous[0]] = total
    return daily


def listing_visitors(this_week: float) -> dict[date, float]:
    return swinging(LISTING_WEEK, base=380, slope=0.2, this_week=this_week)


def sample() -> Report:
    return Report(
        period=REPORT_WEEK,
        generated=datetime(2026, 11, 2, 8, 0),
        apps=(
            AppReport(
                "Example App",
                growth(
                    swinging(BUCKET_WEEK, 120, 0.3, 190),
                    swinging(BUCKET_WEEK, 40, 0.1, 45),
                ),
                listing(listing_visitors(520), rate=0.31),
                reviews_section(
                    swinging(REPORT_WEEK, 4, 0.01, 5),
                    4.2,
                    EXAMPLE_REVIEWS,
                    {5: 14, 4: 9, 3: 5, 2: 2, 1: 3},
                ),
                vitals_section(crash=(0.42, 0.35), anr=(0.21, 0.24)),
                crashlytics_section(98.2, 97.4, EXAMPLE_ISSUES),
                feedback_section(EXAMPLE_FEEDBACK, (5, 5, 2, 7), unhandled=6),
            ),
            AppReport(
                "Second App",
                growth(
                    swinging(BUCKET_WEEK, 60, 0.1, 40),
                    swinging(BUCKET_WEEK, 45, 0.05, 70),
                    data_to=date(2026, 10, 22),
                ),
                listing(listing_visitors(300), rate=0.18, data_to=date(2026, 10, 15)),
                reviews_section(
                    swinging(REPORT_WEEK, 2, 0.01, 2),
                    3.1,
                    EXAMPLE_REVIEWS[1:3],
                    {5: 1, 4: 2, 3: 3, 2: 4, 1: 4},
                    uncovered=(Period(date(2026, 10, 26), date(2026, 10, 27)),),
                ),
                vitals_section(
                    crash=(1.31, 0.98), anr=(0.52, 0.44), data_to=date(2026, 10, 22)
                ),
                crashlytics_section(
                    94.1, 96.3, MANY_ISSUES, data_to=date(2026, 10, 30)
                ),
                feedback_section(
                    many_feedback(),
                    (15, 15, 20, 9),
                    unhandled=41,
                    data_to=date(2026, 10, 30),
                ),
            ),
            AppReport(
                "Third App",
                growth(flat_week(), swinging(BUCKET_WEEK, 20, 0.02, 20)),
                listing(listing_visitors(380), rate=0.2),
                reviews_section({}, 0),
                vitals_section(crash=(1.09, 1.4), anr=(0.3, 0.3)),
                crashlytics_section(99.1, 0, (), trend=1),
                feedback_section((), (0, 0, 3, 1), unhandled=0),
            ),
            AppReport(
                "Fourth App",
                Failure("Play report bucket", "403 Forbidden"),
                Failure("Play report bucket", "403 Forbidden"),
                Failure("Play reviews", "403 Forbidden"),
                Failure("Play vitals", "403 Forbidden"),
                Failure("Crashlytics", "403 Forbidden"),
                Failure("Firestore feedback", "403 Forbidden"),
            ),
            AppReport(
                "Fifth App",
                Unavailable("Play report bucket", BUCKET_WEEK),
                Unavailable("Play report bucket", LISTING_WEEK),
                Unavailable("Play reviews", REPORT_WEEK),
                Unavailable("Play vitals", VITALS_WEEK),
                Unavailable("Crashlytics", CRASHLYTICS_WEEK),
                Unavailable("Firestore feedback", FEEDBACK_WEEK),
            ),
        ),
    )


def main() -> None:
    report = sample()
    html = write(render(report), OUT_DIR)
    pages = pdf.print_pdf(
        pdf.find_chrome(None), html, OUT_DIR / "report.pdf", len(report.apps)
    )
    print(f"HTML: {html}\nPDF:  {OUT_DIR / 'report.pdf'} ({pages} pages)")


if __name__ == "__main__":
    main()
