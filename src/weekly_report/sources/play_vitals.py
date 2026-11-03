"""Play vitals: user-perceived crash and ANR rate from the Play Developer Reporting API.

Days are Pacific Time, the only zone the API supports for daily rows. Each metric set reports
how far its data reaches (`freshnessInfo`), which decides the period when none is requested.
"""

from collections.abc import Callable
from datetime import date, timedelta

from google.oauth2 import service_account
from googleapiclient.discovery import build

from weekly_report.config import AppConfig
from weekly_report.model import Metric, Unavailable, Vitals
from weekly_report.periods import TREND_PERIODS, Coverage, Period, week_ending_by
from weekly_report.sources.play_bucket import SourceError

SOURCE = "Play vitals"
SCOPE = "https://www.googleapis.com/auth/playdeveloperreporting"
TIME_ZONE = "America/Los_Angeles"
CRASH_SET = "crashRateMetricSet"
ANR_SET = "anrRateMetricSet"
CRASH_RATE = "userPerceivedCrashRate"
ANR_RATE = "userPerceivedAnrRate"
WEIGHTED = "28dUserWeighted"

type SetReader = Callable[[str], dict]
type RowReader = Callable[[str, dict], list[dict]]


def pacific_day(day: date) -> dict:
    return {
        "year": day.year,
        "month": day.month,
        "day": day.day,
        "timeZone": {"id": TIME_ZONE},
    }


def last_data_day(metric_set: dict) -> date:
    """The newest day with daily data: freshness is an exclusive end, so the day before it."""
    for freshness in metric_set["freshnessInfo"]["freshnesses"]:
        if freshness["aggregationPeriod"] == "DAILY":
            end = freshness["latestEndTime"]
            return date(end["year"], end["month"], end["day"]) - timedelta(days=1)
    raise SourceError("the metric set reports no daily freshness")


def query_body(rate: str, first: date, last: date) -> dict:
    """Daily rows for the days `first` to `last`, asking for the plain daily rate too: the API
    returns no rows when only a rolling metric is requested."""
    return {
        "metrics": [rate + WEIGHTED, rate],
        "timelineSpec": {
            "aggregationPeriod": "DAILY",
            "startTime": pacific_day(first),
            "endTime": pacific_day(last + timedelta(days=1)),
        },
    }


def daily_values(rows: list[dict], metric: str) -> dict[date, float]:
    values: dict[date, float] = {}
    for row in rows:
        start = row["startTime"]
        for value in row["metrics"]:
            if value["metric"] == metric:
                day = date(start["year"], start["month"], start["day"])
                values[day] = float(value["decimalValue"]["value"])
    return values


def rate_on(daily: dict[date, float]) -> Callable[[date], float]:
    """The rate on a day, or on the newest day before it that has a row."""

    def level(day: date) -> float:
        known = [when for when in daily if when <= day]
        return daily[max(known)] if known else 0.0

    return level


def vitals(
    read_set: SetReader, read_rows: RowReader, period: Period | None = None
) -> Vitals | Unavailable:
    """Crash and ANR rate for `period`, or for the newest complete week both metric sets reach."""
    last = min(last_data_day(read_set(name)) for name in (CRASH_SET, ANR_SET))
    period = period or week_ending_by(last)
    coverage = Coverage.reaching(period, last)
    if coverage is None:
        return Unavailable(SOURCE, period)
    first = period.trailing(TREND_PERIODS)[0].start

    def levels(name: str, rate: str) -> Metric | None:
        body = query_body(rate, first, coverage.covered.end)
        daily = daily_values(read_rows(name, body), rate + WEIGHTED)
        return Metric.level(rate_on(daily), coverage) if daily else None

    crash = levels(CRASH_SET, CRASH_RATE)
    anr = levels(ANR_SET, ANR_RATE)
    if crash is None or anr is None:
        return Unavailable(SOURCE, period)
    return Vitals(coverage, crash_rate=crash, anr_rate=anr)


def readers(app: AppConfig) -> tuple[SetReader, RowReader]:
    credentials = service_account.Credentials.from_service_account_file(
        str(app.service_account_key), scopes=[SCOPE]
    )
    vitals_api = build(
        "playdeveloperreporting", "v1beta1", credentials=credentials
    ).vitals()
    metric_sets = {CRASH_SET: vitals_api.crashrate(), ANR_SET: vitals_api.anrrate()}

    def read_set(name: str) -> dict:
        return metric_sets[name].get(name=f"apps/{app.package}/{name}").execute()

    def read_rows(name: str, body: dict) -> list[dict]:
        response = (
            metric_sets[name]
            .query(name=f"apps/{app.package}/{name}", body=body)
            .execute()
        )
        return response.get("rows", [])

    return read_set, read_rows
