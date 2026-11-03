"""Chart.js configurations, as plain dicts the page turns into JSON."""

from dataclasses import dataclass

from weekly_report.formatting import short_day
from weekly_report.model import Point

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


def day_label(point: Point) -> str:
    return f"{point.day:%a} {point.day.day} {point.day:%b}"


@dataclass(frozen=True)
class Series:
    label: str
    points: tuple[Point, ...]
    colour: str = BLUE


def last_point_only(points: int, radius: float) -> list[float]:
    return [0] * (points - 1) + [radius]


def value_axis(**ticks: int) -> dict:
    return {
        "beginAtZero": True,
        "grace": "10%",
        "grid": {"drawTicks": False},
        "border": {"display": False},
        "ticks": {"maxTicksLimit": 6, **ticks},
    }


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
                    "pointRadius": last_point_only(len(points), 2.5),
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
    y_ticks = {"padding": 6, "precision": 0} if whole_numbers else {"padding": 6}
    return {
        "x": {
            "grid": {"display": False},
            "ticks": {"maxRotation": 0, "autoSkipPadding": 10},
        },
        "y": value_axis(**y_ticks),
    }


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
                    "pointRadius": last_point_only(len(each.points), 3.5),
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
                "x": value_axis(precision=0),
                "y": {"grid": {"display": False}},
            },
        },
    }
