"""Turns a Report into one self-contained HTML page, Chart.js inlined.

The page is a frame every section fills in through three registries: `CARDS` (the number
cards each app opens with), `GLANCE` (the at a glance columns, also the email body) and
`SECTIONS` (each section's cards, from its own template under `templates/sections/`).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from enum import Enum
from importlib.resources import files
from pathlib import Path
from typing import Any

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from weekly_report.model import (
    ANR_THRESHOLD,
    CRASH_THRESHOLD,
    AdMob,
    AppReport,
    Failure,
    Metric,
    Point,
    Report,
    Unavailable,
    Vitals,
)
from weekly_report.periods import TREND_PERIODS

MINUS = "−"
NOT_AVAILABLE = "not available for this range"
NONE = "none"
NO_COMPARISON = "no ratings to compare"
NOTHING_TO_COMPARE = "nothing to compare"
NO_CHANGE = "no change"
BLUE = "#2a78d6"
ORANGE = "#d9622b"
TEAL = "#1a8f72"
GOLD = "#c98a12"
UNIT_COLOURS = (
    BLUE,
    ORANGE,
    TEAL,
    GOLD,
    "#8e5bd6",
    "#c2457a",
    "#5b6b7b",
    "#7fa32a",
    "#2fb0c9",
)


def signed(number: float, digits: int = 0, unit: str = "") -> str:
    rounded = round(number, digits)
    text = f"{abs(rounded):,.{digits}f}{unit}"
    if rounded > 0:
        return f"+{text}"
    if rounded < 0:
        return f"{MINUS}{text}"
    return text


def count(number: float) -> str:
    return f"{number:,.0f}"


def before(days: int) -> str:
    if days == 7:
        return "the week before"
    if days == 1:
        return "the day before"
    return f"the {days} days before"


def periods_of(days: int) -> str:
    if days == 7:
        return "weeks"
    if days == 1:
        return "days"
    return f"periods of {days} days"


def short_day(day: date) -> str:
    return f"{day.day} {day:%b}"


def percent(number: float) -> str:
    return f"{number:.1f}%"


def rate(number: float) -> str:
    return f"{number:.2f}%"


def crash_free(number: float) -> str:
    return rate(number) if number else NONE


def rating(number: float) -> str:
    return f"{number:.2f}" if number else NONE


def money(number: float) -> str:
    return f"{number:,.2f}"


def has_both(metric: Metric) -> bool:
    return metric.value > 0 and metric.previous > 0


def is_comparable(metric: Metric) -> bool:
    return metric.comparable


def no_note(section: Any) -> str:
    return ""


def currency_of(admob: AdMob) -> str:
    return f" {admob.currency}"


@dataclass(frozen=True)
class Change:
    """How a change is written: rounded to `digits` with `unit` after it, and with its percent
    when `percent` is set. A change that rounds to zero is "no change", whatever its size
    before rounding. `unknown` is what stands in when the two values cannot be compared."""

    digits: int = 0
    unit: str = ""
    percent: bool = False
    unknown: str = NOTHING_TO_COMPARE

    def rounded(self, metric: Metric) -> float:
        return round(metric.change, self.digits)

    def text(self, metric: Metric) -> str:
        if self.rounded(metric) == 0:
            return NO_CHANGE
        change = signed(metric.change, self.digits, self.unit)
        if not self.percent or metric.percent_change is None:
            return change
        return f"{change} ({signed(metric.percent_change, 1, '%')})"


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
    change: Change = Change(percent=True)
    comparable: Callable[[Metric], bool] = is_comparable
    note: Callable[[Any], str] = no_note
    unit: Callable[[Any], str] = no_note


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
VITAL_BARS = (
    ("Crash rate", PLAY_CRASH_RATE, CRASH_THRESHOLD),
    ("ANR rate", ANR_RATE, ANR_THRESHOLD),
)
SCALE_PAST_THRESHOLD = 1.5
SCALE_PAST_VALUE = 1.1


@dataclass(frozen=True)
class Bar:
    """One vital against Play's bad behaviour threshold; `fill`, `tick` and `limit` are
    percents of the bar's width, on a scale that always holds the value and the threshold; `tick`
    is None when there is no value from the period before to mark."""

    label: str
    shown: Figure
    threshold: str
    over: bool
    fill: float
    tick: float | None
    limit: float


def bar(label: str, headline: Headline, vitals: Vitals, threshold: float) -> Bar:
    """Play counts a rate of at least the threshold as bad behaviour."""
    metric = headline.metric(vitals)
    scale = max(
        threshold * SCALE_PAST_THRESHOLD,
        max(metric.value, metric.previous) * SCALE_PAST_VALUE,
    )
    return Bar(
        label,
        figure(headline, vitals),
        rate(threshold),
        metric.value >= threshold,
        fill=round(metric.value / scale * 100, 1),
        tick=round(metric.previous / scale * 100, 1) if metric.comparable else None,
        limit=round(threshold / scale * 100, 1),
    )


def bars(vitals: Vitals) -> list[Bar]:
    return [bar(label, each, vitals, limit) for label, each, limit in VITAL_BARS]


def initials(name: str) -> str:
    words = name.replace("-", " ").replace("_", " ").split()
    return "".join(word[0] for word in words[:2]).upper()


def day_label(point: Point) -> str:
    return f"{point.day:%a} {point.day.day} {point.day:%b}"


@dataclass(frozen=True)
class Series:
    label: str
    points: tuple[Point, ...]
    colour: str = BLUE


@dataclass(frozen=True)
class UnitRow:
    name: str
    formats: tuple[str, ...]
    earnings: Cell
    impressions: Cell
    ecpm: Cell


def unit_rows(admob: AdMob) -> list[UnitRow]:
    return [
        UnitRow(
            unit.name,
            unit.formats,
            cell(AD_EARNINGS, unit.earnings),
            cell(AD_IMPRESSIONS, unit.impressions),
            cell(AD_ECPM, unit.ecpm),
        )
        for unit in admob.units
    ]


def unit_series(admob: AdMob) -> tuple[Series, ...]:
    return tuple(
        Series(unit.name, unit.earnings.trend, UNIT_COLOURS[index % len(UNIT_COLOURS)])
        for index, unit in enumerate(admob.units)
    )


def sparkline(points: tuple[Point, ...], colour: str) -> dict:
    return {
        "type": "line",
        "data": {
            "labels": [short_day(point.day) for point in points],
            "datasets": [
                {
                    "data": [point.value for point in points],
                    "borderColor": colour,
                    "backgroundColor": colour + "1f",
                    "fill": "start",
                    "tension": 0.3,
                    "pointRadius": [0] * (len(points) - 1) + [2.5],
                    "pointBackgroundColor": colour,
                    "borderWidth": 1.75,
                }
            ],
        },
        "options": {
            "events": [],
            "layout": {"padding": {"top": 3, "bottom": 1, "right": 3}},
            "plugins": {"legend": {"display": False}, "tooltip": {"enabled": False}},
            "scales": {
                "x": {"display": False},
                "y": {"display": False, "beginAtZero": False, "grace": "8%"},
            },
        },
    }


def axes(whole_numbers: bool = True) -> dict:
    scales = {
        "x": {
            "grid": {"display": False},
            "ticks": {"maxRotation": 0, "autoSkipPadding": 10},
        },
        "y": {
            "beginAtZero": True,
            "grace": "10%",
            "grid": {"drawTicks": False},
            "border": {"display": False},
            "ticks": {"maxTicksLimit": 6, "padding": 6, "precision": 0},
        },
    }
    if not whole_numbers:
        del scales["y"]["ticks"]["precision"]
    return scales


def legend(series: tuple[Series, ...]) -> dict:
    return {"display": len(series) > 1, "position": "top", "align": "start"}


def bar_chart(
    series: tuple[Series, ...],
    labels: list[str],
    stacked: bool = False,
    whole_numbers: bool = True,
) -> dict:
    scales = axes(whole_numbers)
    if stacked:
        scales["x"]["stacked"] = scales["y"]["stacked"] = True
    return {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": each.label,
                    "data": [point.value for point in each.points],
                    "backgroundColor": each.colour,
                    "borderRadius": 0 if stacked else 4,
                    "borderSkipped": "start",
                    "maxBarThickness": 34,
                }
                for each in series
            ],
        },
        "options": {
            "interaction": {"mode": "index", "intersect": False},
            "plugins": {"legend": legend(series)},
            "scales": scales,
        },
    }


def daily_bars(*series: Series) -> dict:
    return bar_chart(series, [day_label(point) for point in series[0].points])


def stacked_bars(*series: Series) -> dict:
    """One layer per series, each period's money stacked into one bar."""
    labels = [short_day(point.day) for point in series[0].points]
    return bar_chart(series, labels, stacked=True, whole_numbers=False)


def monthly_bars(series: Series) -> dict:
    labels = [f"{point.day:%b %Y}" for point in series.points]
    return bar_chart((series,), labels, whole_numbers=False)


def trend_lines(*series: Series) -> dict:
    return {
        "type": "line",
        "data": {
            "labels": [short_day(point.day) for point in series[0].points],
            "datasets": [
                {
                    "label": each.label,
                    "data": [point.value for point in each.points],
                    "borderColor": each.colour,
                    "backgroundColor": each.colour,
                    "tension": 0.25,
                    "pointRadius": [0] * (len(each.points) - 1) + [3.5],
                    "pointBackgroundColor": each.colour,
                }
                for each in series
            ],
        },
        "options": {
            "interaction": {"mode": "index", "intersect": False},
            "plugins": {"legend": legend(series)},
            "scales": axes(),
        },
    }


def star_bars(breakdown: dict[int, int]) -> dict:
    """Horizontal bars, five stars on top, one per star level."""
    return {
        "type": "bar",
        "data": {
            "labels": [f"{level} star" for level in breakdown],
            "datasets": [
                {
                    "data": list(breakdown.values()),
                    "backgroundColor": GOLD,
                    "borderRadius": 4,
                    "borderSkipped": "start",
                    "maxBarThickness": 18,
                }
            ],
        },
        "options": {
            "indexAxis": "y",
            "plugins": {"legend": {"display": False}},
            "scales": {
                "x": {
                    "beginAtZero": True,
                    "grace": "10%",
                    "grid": {"drawTicks": False},
                    "border": {"display": False},
                    "ticks": {"maxTicksLimit": 6, "precision": 0},
                },
                "y": {"grid": {"display": False}},
            },
        },
    }


def render(
    report: Report,
    cards: tuple[Headline, ...] = CARDS,
    glance: tuple[Headline, ...] = GLANCE,
    sections: tuple[Section, ...] = SECTIONS,
) -> str:
    charts: list[tuple[str, dict]] = []

    def canvas(config: dict, aspect: float) -> str:
        canvas_id = f"chart-{len(charts)}"
        config["options"]["aspectRatio"] = aspect
        charts.append((canvas_id, config))
        return canvas_id

    environment = Environment(
        loader=PackageLoader("weekly_report"),
        autoescape=select_autoescape(default_for_string=True, default=True),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    environment.filters |= {
        "signed": signed,
        "count": count,
        "before": before,
        "periods_of": periods_of,
        "short_day": short_day,
        "initials": initials,
    }
    environment.tests |= {
        "failure": lambda section: isinstance(section, Failure),
        "unavailable": lambda section: isinstance(section, Unavailable),
        "missing": lambda shown: isinstance(shown, Missing),
    }
    environment.globals |= {
        "not_available": NOT_AVAILABLE,
        "trend_periods": TREND_PERIODS,
        "canvas": canvas,
        "Series": Series,
        "ORANGE": ORANGE,
        "sparkline": sparkline,
        "daily_bars": daily_bars,
        "stacked_bars": stacked_bars,
        "monthly_bars": monthly_bars,
        "trend_lines": trend_lines,
        "star_bars": star_bars,
        "ratings_figures": RATINGS_FIGURES,
        "feedback_figures": FEEDBACK_FIGURES,
        "admob_figures": ADMOB_FIGURES,
        "unit_rows": unit_rows,
        "unit_series": unit_series,
        "BLUE": BLUE,
        "figures": figures,
        "vitals_bars": bars,
    }
    template = environment.get_template("report.html.j2")
    return template.render(
        report=report,
        cards=cards,
        glance=glance,
        sections=sections,
        charts=charts,
        chart_js=(files("weekly_report") / "vendor" / "chart.umd.min.js").read_text(
            encoding="utf-8"
        ),
    )


def glance_line(shown: Figure | Missing) -> str:
    if isinstance(shown, Missing):
        if shown.failed:
            return f"  {shown.label}: {shown.reason}, see Problems"
        return f"  {shown.label}, {shown.range}: {shown.reason}"
    said = [shown.value, shown.change]
    if shown.verdict != "neutral":
        said.append(shown.verdict)
    return f"  {shown.label}, {shown.range}: {', '.join(said)}"


def summary(report: Report, glance: tuple[Headline, ...] = GLANCE) -> list[str]:
    """The at a glance table as plain text, for the email body and the command line."""
    lines = [f"Weekly app report, {report.period.label()}", ""]
    if report.problems:
        lines.append("Problems:")
        lines += [
            f"  {app}, {failure.source}: {failure.error}"
            for app, failure in report.problems
        ]
        lines.append("")
    for index, app in enumerate(report.apps):
        if index:
            lines.append("")
        lines.append(app.app)
        lines += [glance_line(shown) for shown in figures(app, glance)]
    return lines


def write(html: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "report.html"
    path.write_text(html, encoding="utf-8")
    return path
