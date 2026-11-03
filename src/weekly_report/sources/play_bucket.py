"""Play Console's report bucket: monthly UTF-16 CSVs, one row per day, days with no data missing."""

import csv
import io
from collections.abc import Callable
from datetime import date, timedelta

from google.api_core.exceptions import NotFound
from google.cloud import storage
from google.oauth2 import service_account

from weekly_report.config import AppConfig
from weekly_report.model import Growth, Metric, Unavailable
from weekly_report.periods import TREND_PERIODS, Coverage, Period, week_ending_by

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


def installs_growth(
    read: Reader, package: str, today: date, period: Period | None = None
) -> Growth | Unavailable:
    """New installs for `period`, or for the newest Monday to Sunday week complete in the file."""
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

    if period is None:
        searched = Period(today - timedelta(days=LOOKBACK_DAYS), today).months()
        daily = daily_for(searched)
        if not daily:
            names = ", ".join(f"{month:%Y-%m}" for month in searched)
            raise SourceError(f"no installs rows in the bucket's files for {names}")
        period = week_ending_by(max(daily))
    span = Period(period.trailing(TREND_PERIODS)[0].start, period.end)
    daily = daily_for(span.months())
    coverage = Coverage.reaching(period, max(daily, default=None))
    if coverage is None:
        return Unavailable(SOURCE, period)
    return Growth(coverage=coverage, installs=Metric.summed(daily, coverage))


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
