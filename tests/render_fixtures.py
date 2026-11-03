import json
import re
from datetime import UTC, date, datetime, timedelta

from weekly_report import render as renderer
from weekly_report.headlines import (
    NEW_INSTALLS,
    SECTIONS,
    Headline,
)
from weekly_report.model import (
    AdMob,
    AdUnit,
    AppReport,
    Crashlytics,
    ErrorKind,
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
    Unavailable,
    UserReport,
    Vitals,
)
from weekly_report.periods import Coverage, Period

REPORT_WEEK = Period(date(2026, 10, 26), date(2026, 11, 1))
BUCKET_WEEK = Period(date(2026, 10, 19), date(2026, 10, 25))
LISTING_WEEK = Period(date(2026, 10, 12), date(2026, 10, 18))
GENERATED = datetime(2026, 11, 2, 8, 0)


def weekly_trend(value):
    return tuple(
        Point(date(2026, 8, 3) + timedelta(weeks=week), 40 + week) for week in range(11)
    ) + (Point(date(2026, 10, 19), value),)


def growth(value=69, previous=52, coverage=None, uninstalls=(20, 25)):
    coverage = coverage or Coverage(BUCKET_WEEK)
    series = tuple(Point(day, 10) for day in coverage.covered.days())
    gone, gone_before = uninstalls
    return Growth(
        coverage=coverage,
        installs=Metric(
            value=value, previous=previous, series=series, trend=weekly_trend(value)
        ),
        uninstalls=Metric(
            value=gone,
            previous=gone_before,
            series=tuple(Point(day, 3) for day in coverage.covered.days()),
            trend=weekly_trend(gone),
        ),
        net=Metric(
            value=value - gone,
            previous=previous - gone_before,
            trend=weekly_trend(value - gone),
        ),
    )


def listing(conversion=12.5, previous=10.0, coverage=None):
    return Listing(
        coverage=coverage or Coverage(LISTING_WEEK),
        visitors=Metric(value=400, previous=380),
        acquisitions=Metric(value=50, previous=38),
        conversion=Metric(
            value=conversion, previous=previous, trend=weekly_trend(conversion)
        ),
    )


REVIEWS_WEEK = Period(date(2026, 10, 26), date(2026, 11, 1))


def review(
    text="Works well",
    stars=4,
    label=Label.NEW,
    title="",
    original_text=None,
    language=None,
    reply=None,
    at=datetime(2026, 10, 28, 12, 0),
):
    return Review(stars, title, text, original_text, language, label, at, reply)


def reviews(
    store=3.67,
    previous=3.5,
    average=4.5,
    average_before=4.0,
    count=4,
    count_before=3,
    cards=(),
    uncovered=(),
    coverage=None,
    breakdown=None,
):
    return Reviews(
        coverage=coverage or Coverage(REVIEWS_WEEK),
        store_rating=Metric(store, previous, trend=weekly_trend(store)),
        new_ratings=Metric(count, count_before, trend=weekly_trend(count)),
        new_average=Metric(average, average_before, trend=weekly_trend(average)),
        breakdown=breakdown or {5: 2, 4: 1, 3: 1, 2: 0, 1: 0},
        reviews=tuple(cards),
        uncovered=tuple(uncovered),
    )


VITALS_WEEK = Period(date(2026, 10, 19), date(2026, 10, 25))


def vitals(crash=0.42, crash_before=0.35, anr=0.21, anr_before=0.24, coverage=None):
    return Vitals(
        coverage=coverage or Coverage(VITALS_WEEK),
        crash_rate=Metric(crash, crash_before, trend=weekly_trend(crash)),
        anr_rate=Metric(anr, anr_before, trend=weekly_trend(anr)),
    )


CRASHLYTICS_WEEK = Period(date(2026, 10, 26), date(2026, 11, 1))


def issue(
    title="Widget.render",
    users=3,
    events=7,
    signals=(),
    kind=ErrorKind.FATAL,
    state=IssueState.OPEN,
    subtitle="NullPointerException",
    version="2.3.0",
    link="https://console.example/widget",
):
    return Issue(
        title, subtitle, kind, state, tuple(signals), users, events, version, link
    )


def crashlytics(free=97.5, before=96.0, issues=(), coverage=None):
    return Crashlytics(
        coverage=coverage or Coverage(CRASHLYTICS_WEEK),
        crash_free=Metric(free, before, trend=weekly_trend(free)),
        issues=tuple(issues),
    )


FEEDBACK_WEEK = Period(date(2026, 10, 26), date(2026, 11, 1))


def user_report(
    message="The list is empty after an import",
    kind=ReportKind.BUG,
    at=datetime(2026, 10, 28, 9, 15, tzinfo=UTC),
    app_version="2.4.0",
    android_version=None,
    error=None,
    email=None,
    app_id=None,
    rating=None,
    liked=(),
):
    return UserReport(
        kind,
        at,
        app_version,
        message,
        android_version,
        error,
        email,
        app_id,
        rating,
        tuple(liked),
    )


def suggestion(message="Nice app", rating=4, liked=(), **kwargs):
    return user_report(
        message, ReportKind.FEEDBACK, rating=rating, liked=liked, **kwargs
    )


def feedback(
    new=5,
    new_before=3,
    bugs=2,
    bugs_before=1,
    suggestions=3,
    suggestions_before=2,
    unhandled=4,
    reports=(),
    coverage=None,
):
    return Feedback(
        coverage=coverage or Coverage(FEEDBACK_WEEK),
        new=Metric(new, new_before),
        bugs=Metric(bugs, bugs_before),
        suggestions=Metric(suggestions, suggestions_before),
        unhandled=unhandled,
        reports=tuple(reports),
    )


ADMOB_WEEK = Period(date(2026, 10, 26), date(2026, 11, 1))


def ad_unit(
    name="Home banner",
    formats=("banner",),
    earnings=(6.0, 5.0),
    impressions=(1200, 1000),
    ecpm=(5.0, 5.0),
    stack=(5.0, 6.0),
):
    return AdUnit(
        name,
        tuple(formats),
        earnings=Metric(
            *earnings,
            trend=tuple(
                Point(date(2026, 8, 10) + timedelta(weeks=week), value)
                for week, value in enumerate([*[0] * 10, *stack])
            ),
        ),
        impressions=Metric(*impressions),
        ecpm=Metric(*ecpm),
    )


MONTHS = (
    Point(date(2026, 8, 1), 120.5),
    Point(date(2026, 9, 1), 130.0),
    Point(date(2026, 10, 1), 90.25),
)


def admob(
    earnings=12.34,
    earnings_before=10.0,
    impressions=5000,
    impressions_before=4000,
    ecpm=2.468,
    ecpm_before=2.5,
    currency="USD",
    units=None,
    monthly=MONTHS,
    coverage=None,
):
    return AdMob(
        coverage=coverage or Coverage(ADMOB_WEEK),
        currency=currency,
        earnings=Metric(earnings, earnings_before, trend=weekly_trend(earnings)),
        impressions=Metric(impressions, impressions_before),
        ecpm=Metric(ecpm, ecpm_before),
        units=tuple((ad_unit(),) if units is None else units),
        monthly=tuple(monthly),
    )


def app(
    name,
    growth_section=None,
    listing_section=None,
    reviews_section=None,
    vitals_section=None,
    crashlytics_section=None,
    feedback_section=None,
    admob_section=None,
):
    return AppReport(
        name,
        growth() if growth_section is None else growth_section,
        listing() if listing_section is None else listing_section,
        reviews() if reviews_section is None else reviews_section,
        vitals() if vitals_section is None else vitals_section,
        crashlytics() if crashlytics_section is None else crashlytics_section,
        feedback() if feedback_section is None else feedback_section,
        admob() if admob_section is None else admob_section,
    )


def render(page, cards=(NEW_INSTALLS,), glance=(NEW_INSTALLS,), sections=SECTIONS):
    return renderer.render(page, cards, glance, sections)


def summary(page, glance=(NEW_INSTALLS,)):
    return renderer.summary(page, glance)


def report(*apps, period=REPORT_WEEK):
    return Report(period=period, apps=apps, generated=GENERATED)


def chart_configs(html: str) -> list:
    match = re.search(r"const CHARTS = (.*?);\n", html)
    return json.loads(match.group(1))


def chart(html: str, label: str) -> dict:
    [canvas_id] = re.findall(
        rf'<canvas id="([\w-]+)" role="img" aria-label="{label}"', html
    )
    return dict(chart_configs(html))[canvas_id]


def values(config: dict) -> list:
    return config["data"]["datasets"][0]["data"]


def part(html: str, start: str, end: str = "</section>") -> str:
    begin = html.index(start)
    return html[begin : html.index(end, begin)]


def apps(html: str) -> list[str]:
    return html.split('<section class="app"')[1:]


def cards(html: str) -> list[str]:
    found = []
    for block in re.findall(
        r'<div class="kpis">(.*?)<div class="grid"', html, re.DOTALL
    ):
        found += re.split(r'<div class="kpi[ "]', block)[1:]
    return found


NO_REVIEWS = Unavailable("Play reviews", REVIEWS_WEEK)
NO_ADMOB = Unavailable("AdMob", ADMOB_WEEK)


def installs(better):
    return Headline("Installs", "growth", lambda section: section.installs, better)
