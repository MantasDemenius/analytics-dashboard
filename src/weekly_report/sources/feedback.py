"""Feedback: the reports users send from the app, read from its Firestore collection.

Days are UTC. The tool only reads: it never sets `handled`.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from weekly_report.config import AppConfig
from weekly_report.model import (
    Feedback,
    Metric,
    ReportKind,
    Unavailable,
    UserReport,
)
from weekly_report.periods import Period
from weekly_report.sources.shared import (
    CLOUD_PLATFORM_SCOPE,
    reached,
    service_account_credentials,
)

SOURCE = "Firestore feedback"
KINDS = {"bug": ReportKind.BUG, "feedback": ReportKind.FEEDBACK}

type DocumentReader = Callable[[Period], list[dict]]
type UnhandledCounter = Callable[[], int]


def bounds(window: Period) -> tuple[datetime, datetime]:
    """The UTC instants a query for `window` spans; the end is the next midnight, exclusive."""
    start = datetime.combine(window.start, time.min, UTC)
    return start, start + timedelta(days=window.length)


def user_report(document: dict) -> UserReport:
    return UserReport(
        kind=KINDS[document["kind"]],
        at=document["createdAt"].astimezone(UTC),
        app_version=document["appVersion"],
        message=document["message"],
        android_version=document.get("androidVersion"),
        error=document.get("error") or None,
        email=document.get("email") or None,
        app_id=document.get("appId"),
        rating=document.get("rating"),
        liked=tuple(document.get("liked", ())),
    )


def feedback(
    read: DocumentReader,
    count_unhandled: UnhandledCounter,
    today: date,
    period: Period | None = None,
) -> Feedback | Unavailable:
    """The reports of `period`, or of the week that just ended, and the unhandled count.

    Reports are current to yesterday, so a range reaching today is covered up to yesterday and
    compared with the same days before it. A range that starts today or later is unavailable.
    """
    coverage = reached(SOURCE, period, today - timedelta(days=1))
    if isinstance(coverage, Unavailable):
        return coverage
    period = coverage.period
    covered = coverage.covered
    before = period.previous().cut(covered.length)
    reports = [
        user_report(document) for document in read(Period(before.start, covered.end))
    ]
    now = [each for each in reports if covered.start <= each.at.date() <= covered.end]
    earlier = [each for each in reports if before.start <= each.at.date() <= before.end]

    def count(chosen: list[UserReport], kind: ReportKind | None = None) -> int:
        return sum(1 for each in chosen if kind in (None, each.kind))

    def metric(kind: ReportKind | None = None) -> Metric:
        return Metric(count(now, kind), count(earlier, kind))

    return Feedback(
        coverage=coverage,
        new=metric(),
        bugs=metric(ReportKind.BUG),
        suggestions=metric(ReportKind.FEEDBACK),
        unhandled=count_unhandled(),
        reports=tuple(sorted(now, key=lambda each: each.at, reverse=True)),
    )


def readers(app: AppConfig) -> tuple[DocumentReader, UnhandledCounter]:
    """Read only: the documents created in a window, and the count of those not yet handled."""
    collection = firestore.Client(
        project=app.firebase_project,
        credentials=service_account_credentials(app, CLOUD_PLATFORM_SCOPE),
    ).collection(app.feedback_collection)

    def read(window: Period) -> list[dict]:
        start, end = bounds(window)
        documents = (
            collection.where(filter=FieldFilter("createdAt", ">=", start))
            .where(filter=FieldFilter("createdAt", "<", end))
            .order_by("createdAt")
            .stream()
        )
        return [document.to_dict() for document in documents]

    def count_unhandled() -> int:
        pending = collection.where(filter=FieldFilter("handled", "==", False))
        return int(pending.count().get()[0][0].value)

    return read, count_unhandled
