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
BLUE = "#2a78d6"


def signed(number: float, digits: int = 0, unit: str = "") -> str:
    text = f"{abs(number):,.{digits}f}{unit}"
    if number > 0:
        return f"+{text}"
    if number < 0:
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
    return Figure(
        label=headline.label,
        value=headline.shown(metric.value),
        change=headline.change(metric),
        direction=direction(metric.change),
        verdict=verdict(metric.change, headline.better),
        was=f"{headline.shown(metric.previous)} {before(coverage.covered.length)}",
        range=coverage.label(),
        periods=periods_of(coverage.period.length),
        trend=metric.trend,
        colour=headline.colour,
    )


def figures(app: AppReport, headlines: tuple[Headline, ...]) -> list[Figure | Missing]:
    return [figure(each, getattr(app, each.section)) for each in headlines]


NEW_INSTALLS = Headline(
    "New installs", "growth", lambda growth: growth.installs, Better.UP
)
CARDS = (NEW_INSTALLS,)
GLANCE = (NEW_INSTALLS,)
SECTIONS = (Section("growth", "Play: growth", "growth.html.j2"),)


def initials(name: str) -> str:
    words = name.replace("-", " ").replace("_", " ").split()
    return "".join(word[0] for word in words[:2]).upper()


def day_label(point: Point) -> str:
    return f"{point.day:%a} {point.day.day} {point.day:%b}"


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


def daily_bars(points: tuple[Point, ...], label: str, colour: str = BLUE) -> dict:
    return {
        "type": "bar",
        "data": {
            "labels": [day_label(point) for point in points],
            "datasets": [
                {
                    "label": label,
                    "data": [point.value for point in points],
                    "backgroundColor": colour,
                    "borderRadius": 4,
                    "borderSkipped": "start",
                    "maxBarThickness": 34,
                }
            ],
        },
        "options": {
            "interaction": {"mode": "index", "intersect": False},
            "plugins": {"legend": {"display": False}},
            "scales": axes(),
        },
    }


def trend_lines(points: tuple[Point, ...], label: str, colour: str = BLUE) -> dict:
    return {
        "type": "line",
        "data": {
            "labels": [short_day(point.day) for point in points],
            "datasets": [
                {
                    "label": label,
                    "data": [point.value for point in points],
                    "borderColor": colour,
                    "backgroundColor": colour,
                    "tension": 0.25,
                    "pointRadius": [0] * (len(points) - 1) + [3.5],
                    "pointBackgroundColor": colour,
                }
            ],
        },
        "options": {
            "interaction": {"mode": "index", "intersect": False},
            "plugins": {"legend": {"position": "top", "align": "start"}},
            "scales": axes(),
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
        "sparkline": sparkline,
        "daily_bars": daily_bars,
        "trend_lines": trend_lines,
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
