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

from weekly_report.model import AppReport, Failure, Metric, Point, Report, Unavailable
from weekly_report.periods import TREND_PERIODS

MINUS = "−"
NOT_AVAILABLE = "not available for this range"
NO_RATINGS = "none"
NO_COMPARISON = "no ratings to compare"
BLUE = "#2a78d6"
ORANGE = "#d9622b"
TEAL = "#1a8f72"
GOLD = "#c98a12"


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


def change_text(metric: Metric) -> str:
    if metric.change == 0:
        return "no change"
    if metric.percent_change is None:
        return signed(metric.change)
    return f"{signed(metric.change)} ({signed(metric.percent_change, 1, '%')})"


def percent(number: float) -> str:
    return f"{number:.1f}%"


def points_change(metric: Metric) -> str:
    if metric.change == 0:
        return "no change"
    return signed(metric.change, 1, " pts")


def rating(number: float) -> str:
    return f"{number:.2f}" if number else NO_RATINGS


def stars_change(metric: Metric) -> str:
    if not has_ratings(metric):
        return NO_COMPARISON
    if metric.change == 0:
        return "no change"
    return signed(metric.change, 2, " stars")


def has_ratings(metric: Metric) -> bool:
    return metric.value > 0 and metric.previous > 0


def no_note(section: Any) -> str:
    return ""


class Better(Enum):
    UP = "up"
    DOWN = "down"
    NEITHER = "neither"


@dataclass(frozen=True)
class Headline:
    """A number one section shows as a number card or an at a glance column.

    `section` names the AppReport field holding the section, whose `coverage` gives the range;
    `metric` picks the number from it, and `shown` and `change` format it.
    """

    label: str
    section: str
    metric: Callable[[Any], Metric]
    better: Better
    colour: str = BLUE
    shown: Callable[[float], str] = count
    change: Callable[[Metric], str] = change_text
    comparable: Callable[[Metric], bool] = lambda metric: True
    note: Callable[[Any], str] = no_note


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
    change = metric.change if headline.comparable(metric) else 0
    return Figure(
        label=headline.label,
        value=headline.shown(metric.value),
        change=headline.change(metric),
        direction=direction(change),
        verdict=verdict(change, headline.better),
        was=f"{headline.shown(metric.previous)} {before(coverage.covered.length)}",
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
    change=points_change,
)
STORE_RATING = Headline(
    "Store rating",
    "reviews",
    lambda reviews: reviews.store_rating,
    Better.UP,
    GOLD,
    shown=rating,
    change=stars_change,
    comparable=has_ratings,
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
    change=stars_change,
    comparable=has_ratings,
)
NEW_RATINGS = Headline(
    "New ratings", "reviews", lambda reviews: reviews.new_ratings, Better.UP, GOLD
)
CARDS = (NEW_INSTALLS, UNINSTALLS, NET_GROWTH, LISTING_CONVERSION, STORE_RATING)
GLANCE = (NET_GROWTH, STORE_RATING)
RATINGS_FIGURES = (NEW_RATINGS_AVERAGE, NEW_RATINGS)
SECTIONS = (
    Section("growth", "Play: growth", "growth.html.j2"),
    Section("reviews", "Play: ratings and reviews", "reviews.html.j2"),
)


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


def axes() -> dict:
    return {
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


def legend(series: tuple[Series, ...]) -> dict:
    return {"display": len(series) > 1, "position": "top", "align": "start"}


def daily_bars(*series: Series) -> dict:
    return {
        "type": "bar",
        "data": {
            "labels": [day_label(point) for point in series[0].points],
            "datasets": [
                {
                    "label": each.label,
                    "data": [point.value for point in each.points],
                    "backgroundColor": each.colour,
                    "borderRadius": 4,
                    "borderSkipped": "start",
                    "maxBarThickness": 34,
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
        "trend_lines": trend_lines,
        "star_bars": star_bars,
        "ratings_figures": RATINGS_FIGURES,
        "figures": figures,
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
