"""Play Console's report bucket: monthly UTF-16 CSVs, one row per day, days with no data missing."""

import csv
import io
from collections.abc import Callable
from datetime import date, timedelta

from google.api_core.exceptions import NotFound
from google.cloud import storage

from weekly_report.config import AppConfig
from weekly_report.model import Growth, Listing, Metric, Unavailable
from weekly_report.periods import Period, week_ending_by
from weekly_report.sources.shared import (
    SourceError,
    reached,
    service_account_credentials,
)

SOURCE = "Play report bucket"
INSTALLS = "Daily User Installs"
UNINSTALLS = "Daily User Uninstalls"
VISITORS = "Store listing visitors"
ACQUISITIONS = "Store listing acquisitions"
LOOKBACK_DAYS = 31
SCOPE = "https://www.googleapis.com/auth/devstorage.read_only"

type Reader = Callable[[str], bytes | None]
type UpdatedReader = Callable[[str], date | None]


def installs_path(package: str, month: date) -> str:
    return f"stats/installs/installs_{package}_{month:%Y%m}_overview.csv"


def store_performance_path(package: str, month: date) -> str:
    return (
        f"stats/store_performance/store_performance_{package}_{month:%Y%m}_country.csv"
    )


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


def memoized(read: Reader) -> Reader:
    fetched: dict[str, bytes | None] = {}

    def cached(path: str) -> bytes | None:
        if path not in fetched:
            fetched[path] = read(path)
        return fetched[path]

    return cached


def daily_column(
    read: Reader, path_for: Callable[[date], str], span: Period, column: str
) -> dict[date, int]:
    """`column` summed per day over the monthly files `span` touches; absent files add nothing."""
    daily: dict[date, int] = {}
    for month in span.months():
        raw = read(path_for(month))
        if raw is not None:
            daily |= daily_totals(raw, column)
    return daily


def reporting_period(
    read: Reader,
    path_for: Callable[[date], str],
    column: str,
    today: date,
    period: Period | None,
) -> Period:
    """`period`, or the newest Monday to Sunday week complete in the files' `column`."""
    if period is not None:
        return period
    searched = Period(today - timedelta(days=LOOKBACK_DAYS), today)
    daily = daily_column(read, path_for, searched, column)
    if not daily:
        names = ", ".join(f"{month:%Y-%m}" for month in searched.months())
        raise SourceError(f"no rows in the bucket's files for {names}")
    return week_ending_by(max(daily))


def with_trend(period: Period) -> Period:
    return Period(period.trend_start(), period.end)


def growth(
    read: Reader, package: str, today: date, period: Period | None = None
) -> Growth | Unavailable:
    """Installs, uninstalls and net growth for `period`, or for the newest complete week."""
    read = memoized(read)

    def path_for(month: date) -> str:
        return installs_path(package, month)

    period = reporting_period(read, path_for, INSTALLS, today, period)
    span = with_trend(period)
    installs = daily_column(read, path_for, span, INSTALLS)
    coverage = reached(SOURCE, period, max(installs, default=None))
    if isinstance(coverage, Unavailable):
        return coverage
    uninstalls = daily_column(read, path_for, span, UNINSTALLS)
    net = {
        day: installs.get(day, 0) - uninstalls.get(day, 0)
        for day in installs.keys() | uninstalls.keys()
    }
    return Growth(
        coverage=coverage,
        installs=Metric.summed(installs, coverage),
        uninstalls=Metric.summed(uninstalls, coverage),
        net=Metric.summed(net, coverage),
    )


def listing(
    read: Reader, package: str, today: date, period: Period | None = None
) -> Listing | Unavailable:
    """Store listing visitors, acquisitions and conversion for `period`, or the newest complete week."""
    read = memoized(read)

    def path_for(month: date) -> str:
        return store_performance_path(package, month)

    period = reporting_period(read, path_for, VISITORS, today, period)
    span = with_trend(period)
    visitors = daily_column(read, path_for, span, VISITORS)
    coverage = reached(SOURCE, period, max(visitors, default=None))
    if isinstance(coverage, Unavailable):
        return coverage
    visited = Metric.summed(visitors, coverage)
    acquired = Metric.summed(daily_column(read, path_for, span, ACQUISITIONS), coverage)
    return Listing(
        coverage=coverage,
        visitors=visited,
        acquisitions=acquired,
        conversion=Metric.ratio(acquired, visited),
    )


def bucket_of(app: AppConfig) -> storage.Bucket:
    return storage.Client(
        project=app.firebase_project,
        credentials=service_account_credentials(app, SCOPE),
    ).bucket(app.play_bucket)


def bucket_updated(app: AppConfig) -> UpdatedReader:
    """The day, in UTC, each file in the bucket was last written, or None for an absent file."""
    bucket = bucket_of(app)

    def updated(path: str) -> date | None:
        blob = bucket.get_blob(path)
        return blob.updated.date() if blob else None

    return updated


def bucket_reader(app: AppConfig) -> Reader:
    bucket = bucket_of(app)

    def read(path: str) -> bytes | None:
        try:
            return bucket.blob(path).download_as_bytes()
        except NotFound:
            return None

    return read
