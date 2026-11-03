"""AdMob: earnings and impressions from the AdMob API's `networkReport`.

Days are Pacific Time, the only zone AdMob reports in. One call by day, ad unit and format
gives the range, and one by month gives the earnings growth. The report needs no ad unit list:
every row carries its unit's id and name.
"""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from weekly_report.model import AdMob, AdUnit, Metric, Point, Unavailable
from weekly_report.periods import Coverage, Period
from weekly_report.sources.shared import reached

SOURCE = "AdMob"
TOKEN_FILE = Path("config/admob-token.json")
MICROS = 1_000_000
PER_THOUSAND = 1000
MONTHS_SHOWN = 24
METRICS = ["ESTIMATED_EARNINGS", "IMPRESSIONS"]

type ReportReader = Callable[[dict], list[dict]]


def api_date(day: date) -> dict:
    return {"year": day.year, "month": day.month, "day": day.day}


def spec(dimensions: list[str], first: date, last: date) -> dict:
    return {
        "reportSpec": {
            "dateRange": {"startDate": api_date(first), "endDate": api_date(last)},
            "dimensions": dimensions,
            "metrics": METRICS,
        }
    }


def month_after(month: date) -> date:
    return (month + timedelta(days=32)).replace(day=1)


def monthly_range(last_day: date) -> tuple[date, date]:
    """The `MONTHS_SHOWN` complete calendar months up to `last_day`, the month it falls in
    counting only when `last_day` is its last day."""
    this_month = last_day.replace(day=1)
    last_month = (
        this_month
        if month_after(this_month) - timedelta(days=1) == last_day
        else (this_month - timedelta(days=1)).replace(day=1)
    )
    first = last_month
    for _ in range(MONTHS_SHOWN - 1):
        first = (first - timedelta(days=1)).replace(day=1)
    return first, month_after(last_month) - timedelta(days=1)


def header_currency(messages: list[dict]) -> str:
    for message in messages:
        if "header" in message:
            return message["header"]["localizationSettings"]["currencyCode"]
    raise ValueError("the report has no header")


def rows(messages: list[dict]) -> list[dict]:
    return [message["row"] for message in messages if "row" in message]


def money_metric(row: dict, metric: str) -> float:
    return int(row["metricValues"][metric]["microsValue"]) / MICROS


def integer_metric(row: dict, metric: str) -> int:
    return int(row["metricValues"][metric]["integerValue"])


def report_date(text: str) -> date:
    return date(int(text[:4]), int(text[4:6]), int(text[6:]))


@dataclass
class Daily:
    """What one ad unit earned and showed on each day it has a row."""

    name: str
    formats: set[str] = field(default_factory=set)
    earnings: dict[date, float] = field(default_factory=lambda: defaultdict(float))
    impressions: dict[date, float] = field(default_factory=lambda: defaultdict(float))


def daily_units(messages: list[dict]) -> dict[str, Daily]:
    units: dict[str, Daily] = {}
    for row in rows(messages):
        dimensions = row["dimensionValues"]
        unit = dimensions["AD_UNIT"]
        daily = units.setdefault(unit["value"], Daily(unit["displayLabel"]))
        day = report_date(dimensions["DATE"]["value"])
        daily.formats.add(dimensions["FORMAT"]["value"])
        daily.earnings[day] += money_metric(row, "ESTIMATED_EARNINGS")
        daily.impressions[day] += integer_metric(row, "IMPRESSIONS")
    return units


def summed(days: list[dict[date, float]]) -> dict[date, float]:
    total: dict[date, float] = defaultdict(float)
    for each in days:
        for day, value in each.items():
            total[day] += value
    return total


def monthly_earnings(messages: list[dict]) -> tuple[Point, ...]:
    points = []
    for row in rows(messages):
        month = row["dimensionValues"]["MONTH"]["value"]
        points.append(
            Point(
                date(int(month[:4]), int(month[4:]), 1),
                money_metric(row, "ESTIMATED_EARNINGS"),
            )
        )
    return tuple(sorted(points, key=lambda point: point.day))


def ad_unit(daily: Daily, coverage: Coverage) -> AdUnit:
    earnings = Metric.summed(daily.earnings, coverage)
    impressions = Metric.summed(daily.impressions, coverage)
    return AdUnit(
        daily.name,
        tuple(sorted(daily.formats)),
        earnings,
        impressions,
        Metric.ratio(earnings, impressions, per=PER_THOUSAND),
    )


def admob(
    read: ReportReader, today: date, period: Period | None = None
) -> AdMob | Unavailable:
    coverage = reached(SOURCE, period, today - timedelta(days=1))
    if isinstance(coverage, Unavailable):
        return coverage
    first = coverage.period.trend_start()
    messages = read(spec(["DATE", "AD_UNIT", "FORMAT"], first, coverage.covered.end))
    monthly = read(spec(["MONTH"], *monthly_range(coverage.covered.end)))
    units = daily_units(messages).values()
    earnings = Metric.summed(summed([unit.earnings for unit in units]), coverage)
    impressions = Metric.summed(summed([unit.impressions for unit in units]), coverage)
    return AdMob(
        coverage,
        header_currency(messages),
        earnings=earnings,
        impressions=impressions,
        ecpm=Metric.ratio(earnings, impressions, per=PER_THOUSAND),
        units=tuple(
            sorted(
                (ad_unit(unit, coverage) for unit in units),
                key=lambda unit: (-unit.earnings.value, unit.name),
            )
        ),
        monthly=monthly_earnings(monthly),
    )


def reader(publisher: str) -> ReportReader:
    """Signs in with the saved AdMob token and runs one report spec per call."""
    credentials = Credentials.from_authorized_user_file(str(TOKEN_FILE))
    reports = build("admob", "v1", credentials=credentials).accounts().networkReport()

    def read(body: dict) -> list[dict]:
        return reports.generate(parent=f"accounts/{publisher}", body=body).execute()

    return read
