"""Turns a Report into one self-contained HTML page, Chart.js inlined."""

from importlib.resources import files
from pathlib import Path

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from weekly_report.model import Failure, Metric, Point, Report

MINUS = "−"
INSTALLS_COLOUR = "#2a6fdb"


def signed(number: float, digits: int = 0, unit: str = "") -> str:
    text = f"{abs(number):,.{digits}f}{unit}"
    if number > 0:
        return f"+{text}"
    if number < 0:
        return f"{MINUS}{text}"
    return text


def count(number: float) -> str:
    return f"{number:,.0f}"


def day_label(point: Point) -> str:
    return f"{point.day:%a} {point.day.day} {point.day:%b}"


def bar_chart(points: tuple[Point, ...], label: str) -> dict:
    return {
        "type": "bar",
        "data": {
            "labels": [day_label(point) for point in points],
            "datasets": [
                {
                    "label": label,
                    "data": [point.value for point in points],
                    "backgroundColor": INSTALLS_COLOUR,
                }
            ],
        },
        "options": {
            "aspectRatio": 2.6,
            "plugins": {"legend": {"display": False}},
            "scales": {
                "y": {"beginAtZero": True, "grace": "10%", "ticks": {"precision": 0}}
            },
        },
    }


def render(report: Report) -> str:
    charts: list[tuple[str, dict]] = []

    def chart(points: tuple[Point, ...], label: str) -> str:
        canvas_id = f"chart-{len(charts)}"
        charts.append((canvas_id, bar_chart(points, label)))
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
    }
    environment.tests["failure"] = lambda section: isinstance(section, Failure)
    template = environment.get_template("report.html.j2")
    return template.render(
        report=report,
        chart=chart,
        charts=charts,
        chart_js=(files("weekly_report") / "vendor" / "chart.umd.min.js").read_text(
            encoding="utf-8"
        ),
    )


def change_text(metric: Metric) -> str:
    if metric.percent_change is None:
        return signed(metric.change)
    return f"{signed(metric.change)}, {signed(metric.percent_change, 1, '%')}"


def summary(report: Report) -> list[str]:
    """Plain text lines with numbers only, for the email body and the command line."""
    lines = [f"Weekly app report, {report.period.label()}", ""]
    if report.problems:
        lines.append("Problems:")
        lines += [
            f"  {app}, {failure.source}: {failure.error}"
            for app, failure in report.problems
        ]
        lines.append("")
    for app in report.apps:
        lines.append(app.app)
        growth = app.growth
        if isinstance(growth, Failure):
            lines.append(f"  {growth.source} failed, see Problems")
        else:
            installs = growth.installs
            lines.append(
                f"  New installs, {growth.period.label()}: "
                f"{count(installs.value)} ({change_text(installs)})"
            )
    return lines


def write(html: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "report.html"
    path.write_text(html, encoding="utf-8")
    return path
