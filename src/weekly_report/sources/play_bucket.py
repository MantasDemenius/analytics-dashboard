"""Play Console's report bucket: monthly UTF-16 CSVs, one row per day, days with no data missing."""

import csv
import io
from collections.abc import Callable
from datetime import date, timedelta

from google.api_core.exceptions import NotFound
from google.cloud import storage
from google.oauth2 import service_account

from weekly_report.config import AppConfig
from weekly_report.model import Growth, Metric, Point
from weekly_report.periods import Period, week_ending_by

SOURCE = "Play report bucket"
INSTALLS = "Daily User Installs"
LOOKBACK_DAYS = 31

type Reader = Callable[[str], bytes | None]


class SourceError(Exception):
    pass


def installs_path(package: str, month: date) -> str:
    return f"stats/installs/installs_{package}_{month:%Y%m}_overview.csv"


def daily_totals(raw: bytes, column: str) -> dict[date, int]:
    """Sums `column` per day over a report file's rows."""
    rows = csv.DictReader(io.StringIO(raw.decode("utf-16")))
    if rows.fieldnames is not None and column not in rows.fieldnames:
        raise SourceError(f"the report file has no '{column}' column")
    totals: dict[date, int] = {}
    for row in rows:
        day = date.fromisoformat(row["Date"])
        totals[day] = totals.get(day, 0) + int(row[column])
    return totals


def summarise(daily: dict[date, int], period: Period) -> Metric:
    """The period's total against the period before, a missing day counting as zero."""
    series = tuple(Point(day, daily.get(day, 0)) for day in period.days())
    previous = sum(daily.get(day, 0) for day in period.previous().days())
    return Metric(
        value=sum(point.value for point in series), previous=previous, series=series
    )


def installs_growth(read: Reader, package: str, today: date) -> Growth:
    """New installs for the newest Monday to Sunday week complete in the installs file."""
    files: dict[date, bytes | None] = {}

    def daily_for(months: list[date]) -> dict[date, int]:
        for month in months:
            if month not in files:
                files[month] = read(installs_path(package, month))
        daily: dict[date, int] = {}
        for raw in files.values():
            if raw is not None:
                daily |= daily_totals(raw, INSTALLS)
        return daily

    searched = Period(today - timedelta(days=LOOKBACK_DAYS), today).months()
    daily = daily_for(searched)
    if not daily:
        names = ", ".join(f"{month:%Y-%m}" for month in searched)
        raise SourceError(f"no installs rows in the bucket's files for {names}")
    period = week_ending_by(max(daily))
    daily = daily_for(Period(period.previous().start, period.end).months())
    return Growth(period=period, installs=summarise(daily, period))


def bucket_reader(app: AppConfig) -> Reader:
    credentials = service_account.Credentials.from_service_account_file(
        str(app.service_account_key),
        scopes=["https://www.googleapis.com/auth/devstorage.read_only"],
    )
    bucket = storage.Client(
        project=app.firebase_project, credentials=credentials
    ).bucket(app.play_bucket)

    def read(path: str) -> bytes | None:
        try:
            return bucket.blob(path).download_as_bytes()
        except NotFound:
            return None

    return read
