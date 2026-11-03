"""The numbers the report headlines, and the registries of where each one is shown.

A `Headline` is one number from one section, drawn as a number card or an at a glance column.
`CARDS` is the number cards each app opens with, `GLANCE` the at a glance columns (also the
email body) and `SECTIONS` each section's cards, from its own template under
`templates/sections/`.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from weekly_report.charts import BLUE, GOLD, ORANGE, TEAL
from weekly_report.formatting import (
    NO_COMPARISON,
    NONE,
    NOT_AVAILABLE,
    WHOLE_PERCENT_CHANGE,
    Change,
    before,
    count,
    crash_free,
    money,
    percent,
    periods_of,
    rate,
    rating,
    short_day,
    signed,
)
from weekly_report.model import AdMob, AppReport, Failure, Metric, Point, Unavailable


def has_both(metric: Metric) -> bool:
    return metric.value > 0 and metric.previous > 0


def is_comparable(metric: Metric) -> bool:
    return metric.comparable


def no_text(section: Any) -> str:
    return ""


def currency_of(admob: AdMob) -> str:
    return f" {admob.currency}"


class Better(Enum):
    UP = "up"
    DOWN = "down"
    NEITHER = "neither"


@dataclass(frozen=True)
class Headline:
    """A number one section shows as a number card or an at a glance column.

    `section` names the AppReport field holding the section, whose `coverage` gives the range;
    `metric` picks the number from it, `shown` formats a value and `change` the change; `unit`
    is appended to every value `shown` formats.
    """

    label: str
    section: str
    metric: Callable[[Any], Metric]
    better: Better
    colour: str = BLUE
    shown: Callable[[float], str] = count
    change: Change = WHOLE_PERCENT_CHANGE
    comparable: Callable[[Metric], bool] = is_comparable
    note: Callable[[Any], str] = no_text
    unit: Callable[[Any], str] = no_text


@dataclass(frozen=True)
class Section:
    """One AppReport field and the template under `templates/sections/` that draws it."""

    field: str
    title: str
    template: str


@dataclass(frozen=True)
class Figure:
    label: str
    value: str
    change: str
    direction: str
    verdict: str
    was: str
    range: str
    periods: str
    trend: tuple[Point, ...]
    colour: str = BLUE
    note: str = ""


@dataclass(frozen=True)
class Cell:
    """A number and its change as a table cell shows them."""

    value: str
    change: str
    direction: str
    verdict: str


@dataclass(frozen=True)
class Missing:
    label: str
    range: str
    reason: str
    failed: bool


def direction(change: float) -> str:
    if change > 0:
        return "up"
    if change < 0:
        return "down"
    return "flat"


def verdict(change: float, better: Better) -> str:
    if change == 0 or better is Better.NEITHER:
        return "neutral"
    return "better" if (change > 0) == (better is Better.UP) else "worse"


def cell(headline: Headline, metric: Metric) -> Cell:
    shown = headline.shown(metric.value)
    if not headline.comparable(metric):
        return Cell(shown, headline.change.unknown, "flat", "neutral")
    change = headline.change.rounded(metric)
    return Cell(
        shown,
        headline.change.text(metric),
        direction(change),
        verdict(change, headline.better),
    )


def figure(headline: Headline, section: Any) -> Figure | Missing:
    """How one headline shows for one app's section, or why it cannot."""
    if isinstance(section, Failure):
        return Missing(headline.label, "", f"{section.source} failed", failed=True)
    if isinstance(section, Unavailable):
        return Missing(
            headline.label, section.period.label(), NOT_AVAILABLE, failed=False
        )
    metric = headline.metric(section)
    coverage = section.coverage
    shown = cell(headline, metric)
    unit = headline.unit(section)
    was = f"{headline.shown(metric.previous)}{unit}" if metric.comparable else NONE
    return Figure(
        label=headline.label,
        value=shown.value + unit,
        change=shown.change,
        direction=shown.direction,
        verdict=shown.verdict,
        was=f"{was} {before(coverage.covered.length)}",
        range=coverage.label(),
        periods=periods_of(coverage.period.length),
        trend=metric.trend,
        colour=headline.colour,
        note=headline.note(section),
    )


def figures(app: AppReport, headlines: tuple[Headline, ...]) -> list[Figure | Missing]:
    return [figure(each, getattr(app, each.section)) for each in headlines]


NEW_INSTALLS = Headline(
    "New installs", "growth", lambda growth: growth.installs, Better.UP
)
UNINSTALLS = Headline(
    "Uninstalls", "growth", lambda growth: growth.uninstalls, Better.DOWN, ORANGE
)
NET_GROWTH = Headline(
    "Net growth", "growth", lambda growth: growth.net, Better.UP, TEAL, shown=signed
)
LISTING_CONVERSION = Headline(
    "Listing conversion",
    "listing",
    lambda listing: listing.conversion,
    Better.UP,
    shown=percent,
    change=Change(1, " pts"),
)
STORE_RATING = Headline(
    "Store rating",
    "reviews",
    lambda reviews: reviews.store_rating,
    Better.UP,
    GOLD,
    shown=rating,
    change=Change(2, " stars", unknown=NO_COMPARISON),
    comparable=has_both,
    note=lambda reviews: (
        f"28 day average rating, as of {short_day(reviews.coverage.covered.end)}"
    ),
)
NEW_RATINGS_AVERAGE = Headline(
    "Average of new ratings",
    "reviews",
    lambda reviews: reviews.new_average,
    Better.UP,
    GOLD,
    shown=rating,
    change=Change(2, " stars", unknown=NO_COMPARISON),
    comparable=has_both,
)
NEW_RATINGS = Headline(
    "New ratings", "reviews", lambda reviews: reviews.new_ratings, Better.UP, GOLD
)
PLAY_CRASH_RATE = Headline(
    "Play crash rate",
    "vitals",
    lambda vitals: vitals.crash_rate,
    Better.DOWN,
    ORANGE,
    shown=rate,
    change=Change(2, " pts"),
    note=lambda vitals: (
        f"User-perceived, 28 days, as of {short_day(vitals.coverage.covered.end)}"
    ),
)
ANR_RATE = Headline(
    "ANR rate",
    "vitals",
    lambda vitals: vitals.anr_rate,
    Better.DOWN,
    ORANGE,
    shown=rate,
    change=Change(2, " pts"),
)
CRASH_FREE_USERS = Headline(
    "Crash free users",
    "crashlytics",
    lambda crashlytics: crashlytics.crash_free,
    Better.UP,
    TEAL,
    shown=crash_free,
    change=Change(2, " pts"),
    comparable=has_both,
    note=lambda crashlytics: "Users without fatal crashes, UTC days",
)
NEW_FEEDBACK = Headline(
    "New feedback", "feedback", lambda feedback: feedback.new, Better.NEITHER, TEAL
)
BUG_REPORTS = Headline(
    "Bug reports", "feedback", lambda feedback: feedback.bugs, Better.DOWN, ORANGE
)
FEEDBACK_MESSAGES = Headline(
    "Feedback", "feedback", lambda feedback: feedback.suggestions, Better.NEITHER, TEAL
)
AD_EARNINGS = Headline(
    "Ad earnings",
    "admob",
    lambda admob: admob.earnings,
    Better.UP,
    shown=money,
    change=Change(2, percent=True),
    unit=currency_of,
    note=lambda admob: "Estimated, Pacific Time days",
)
AD_IMPRESSIONS = Headline(
    "Impressions", "admob", lambda admob: admob.impressions, Better.UP
)
AD_ECPM = Headline(
    "eCPM",
    "admob",
    lambda admob: admob.ecpm,
    Better.UP,
    shown=money,
    change=Change(2, percent=True),
    unit=currency_of,
)
CARDS = (
    NEW_INSTALLS,
    UNINSTALLS,
    NET_GROWTH,
    LISTING_CONVERSION,
    STORE_RATING,
    CRASH_FREE_USERS,
    PLAY_CRASH_RATE,
    AD_EARNINGS,
)
GLANCE = (
    NET_GROWTH,
    STORE_RATING,
    CRASH_FREE_USERS,
    PLAY_CRASH_RATE,
    NEW_FEEDBACK,
    AD_EARNINGS,
)
RATINGS_FIGURES = (NEW_RATINGS_AVERAGE, NEW_RATINGS)
FEEDBACK_FIGURES = (BUG_REPORTS, FEEDBACK_MESSAGES)
ADMOB_FIGURES = (AD_EARNINGS, AD_IMPRESSIONS, AD_ECPM)
SECTIONS = (
    Section("growth", "Play: growth", "growth.html.j2"),
    Section("reviews", "Play: ratings and reviews", "reviews.html.j2"),
    Section("vitals", "Play: vitals", "vitals.html.j2"),
    Section("crashlytics", "Crashlytics: issues", "crashlytics.html.j2"),
    Section("feedback", "User feedback", "feedback.html.j2"),
    Section("admob", "AdMob: ad earnings", "admob.html.j2"),
)
