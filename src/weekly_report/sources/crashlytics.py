"""Crashlytics: crash free users and every issue, from the Crashlytics REST API (`v1alpha`).

Days are UTC. The API only looks back 90 calendar days, and `topIssues` pages with
`nextPageToken` and returns no `totalSize`.
"""

from collections.abc import Callable
from datetime import date, timedelta

from google.oauth2 import service_account
from googleapiclient.discovery import build

from weekly_report.config import AppConfig
from weekly_report.model import (
    Crashlytics,
    ErrorKind,
    Issue,
    IssueState,
    Metric,
    Point,
    Signal,
    Unavailable,
)
from weekly_report.periods import TREND_PERIODS, Coverage, Period, week_ending_by

SOURCE = "Crashlytics"
SCOPE = "https://www.googleapis.com/auth/cloud-platform"
DISCOVERY = "https://firebasecrashlytics.googleapis.com/$discovery/rest?version=v1alpha"
WINDOW_DAYS = 90
PAGE_SIZE = 100
TOP_ISSUES = "topIssues"
APP_SUMMARY = "appSummary"

type ReportReader = Callable[[str, Period, str | None], dict]


def utc_midnight(day: date) -> str:
    return f"{day.isoformat()}T00:00:00Z"


def query(report: str, period: Period, token: str | None) -> dict:
    """The client's keyword arguments for one page of `report` over `period`.

    The interval ends at the next midnight because the API's end is exclusive. The crash free
    figure counts fatal crashes only, which is what the Firebase console's card shows.
    """
    asked: dict = {
        "pageSize": PAGE_SIZE,
        "filter_interval_startTime": utc_midnight(period.start),
        "filter_interval_endTime": utc_midnight(period.end + timedelta(days=1)),
    }
    if token:
        asked["pageToken"] = token
    if report == APP_SUMMARY:
        asked["filter_issue_errorTypes"] = ["FATAL"]
    return asked


def signals_of(raw: list[dict]) -> tuple[Signal, ...]:
    named = {entry["signal"].removeprefix("SIGNAL_") for entry in raw}
    return tuple(signal for signal in Signal if signal.name in named)


def issue(group: dict) -> Issue:
    """One `topIssues` group; its counts are those of the interval asked for."""
    raw = group["issue"]
    counts = group["metrics"][0] if group.get("metrics") else {}
    return Issue(
        title=raw["title"],
        subtitle=raw.get("subtitle", ""),
        kind=ErrorKind[raw["errorType"]],
        state=IssueState[raw["state"]],
        signals=signals_of(raw.get("signals", [])),
        users=int(counts.get("impactedUsersCount", 0)),
        events=int(counts.get("eventsCount", 0)),
        first_seen_version=raw.get("firstSeenVersion"),
        link=raw.get("uri"),
    )


def sorted_issues(issues: list[Issue]) -> tuple[Issue, ...]:
    """New and regressed issues first, then by users affected, events breaking ties."""
    return tuple(
        sorted(
            issues,
            key=lambda each: (not each.needs_attention, -each.users, -each.events),
        )
    )


def all_groups(read: ReportReader, period: Period) -> list[dict]:
    """Every `topIssues` group across the pages, following `nextPageToken` to the last."""
    found: list[dict] = []
    token = None
    while True:
        page = read(TOP_ISSUES, period, token)
        found += page.get("groups", [])
        token = page.get("nextPageToken")
        if not token:
            return found


def crash_free_users(read: ReportReader, period: Period) -> float:
    """The percent of users with no fatal crash in `period`; 0 when Crashlytics counted no users."""
    groups = read(APP_SUMMARY, period, None).get("groups", [])
    return (
        groups[0]["metrics"][0].get("crashFreeUsersPercentage", 0.0) if groups else 0.0
    )


def crashlytics(
    read: ReportReader, today: date, period: Period | None = None
) -> Crashlytics | Unavailable:
    """Crash free users and every issue for `period`, or for the week that just ended.

    Crashlytics holds the last 90 days and is current to yesterday. A range that starts before
    the 90 days is unavailable; a comparison or trend period that does, is left out.
    """
    period = period or week_ending_by(today - timedelta(days=1))
    oldest = today - timedelta(days=WINDOW_DAYS)
    coverage = Coverage.reaching(period, today - timedelta(days=1))
    if coverage is None or period.start < oldest:
        return Unavailable(SOURCE, period)
    days = coverage.covered.length
    levels = {
        each.start: crash_free_users(read, each.cut(days))
        for each in period.trailing(TREND_PERIODS)
        if each.start >= oldest
    }
    return Crashlytics(
        coverage=coverage,
        crash_free=Metric(
            value=levels[period.start],
            previous=levels.get(period.previous().start, 0.0),
            trend=tuple(
                Point(start, level) for start, level in levels.items() if level
            ),
        ),
        issues=sorted_issues(
            [issue(group) for group in all_groups(read, coverage.covered)]
        ),
    )


def reader(app: AppConfig) -> ReportReader:
    credentials = service_account.Credentials.from_service_account_file(
        str(app.service_account_key), scopes=[SCOPE]
    )
    reports = (
        build(
            "firebasecrashlytics",
            "v1alpha",
            credentials=credentials,
            discoveryServiceUrl=DISCOVERY,
            static_discovery=False,
        )
        .projects()
        .apps()
        .reports()
    )
    parent = f"projects/{app.firebase_project}/apps/{app.firebase_app_id}/reports"

    def read(report: str, period: Period, token: str | None) -> dict:
        return reports.get(
            name=f"{parent}/{report}", **query(report, period, token)
        ).execute()

    return read
