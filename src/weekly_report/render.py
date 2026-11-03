"""Turns a Report into one self-contained HTML page, Chart.js inlined, and into the plain text
summary the email and the command line print.

The page is a frame every section fills in through the registries in `headlines`.
"""

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from weekly_report.charts import (
    BLUE,
    ORANGE,
    UNIT_COLOURS,
    Series,
    daily_bars,
    monthly_bars,
    sparkline,
    stacked_bars,
    star_bars,
    trend_lines,
)
from weekly_report.formatting import (
    NOT_AVAILABLE,
    before,
    count,
    periods_of,
    rate,
    short_day,
    signed,
)
from weekly_report.headlines import (
    AD_EARNINGS,
    AD_ECPM,
    AD_IMPRESSIONS,
    ADMOB_FIGURES,
    ANR_RATE,
    CARDS,
    FEEDBACK_FIGURES,
    GLANCE,
    PLAY_CRASH_RATE,
    RATINGS_FIGURES,
    SECTIONS,
    Cell,
    Figure,
    Headline,
    Missing,
    Section,
    cell,
    figure,
    figures,
)
from weekly_report.model import (
    ANR_THRESHOLD,
    CRASH_THRESHOLD,
    AdMob,
    Failure,
    Report,
    Unavailable,
    Vitals,
)
from weekly_report.periods import TREND_PERIODS

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
