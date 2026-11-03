"""Play ratings and reviews: the reviews CSV in the report bucket, merged with the Reviews API.

The CSV holds every rating, star-only ones included, and lags a few days. The API holds only
reviews with text, from the last 7 days, with no lag. A review in both is merged by its id.
"""

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urlparse

from googleapiclient.discovery import build

from weekly_report.config import AppConfig
from weekly_report.model import Label, Metric, Review, Reviews, Unavailable
from weekly_report.periods import Period, week_ending_by
from weekly_report.sources.play_bucket import Reader, memoized
from weekly_report.sources.shared import (
    SourceError,
    reached,
    service_account_credentials,
)

SOURCE = "Play reviews"
SCOPE = "https://www.googleapis.com/auth/androidpublisher"
STAR_LEVELS = (5, 4, 3, 2, 1)
STORE_RATING_DAYS = 28
API_DAYS = 7
TRANSLATION_LANGUAGE = "en_US"
REQUIRED_COLUMNS = (
    "Reviewer Language",
    "Review Submit Date and Time",
    "Review Last Update Date and Time",
    "Star Rating",
    "Review Title",
    "Review Text",
    "Developer Reply Text",
    "Review Link",
)

type ApiReader = Callable[[], list[dict]]
type PageReader = Callable[[str | None], dict]


@dataclass(frozen=True)
class CsvReview:
    review_id: str | None
    stars: int
    title: str
    text: str
    language: str
    submitted: datetime
    updated: datetime
    reply: str | None

    @property
    def has_text(self) -> bool:
        return bool(self.title or self.text)


@dataclass(frozen=True)
class ApiReview:
    review_id: str
    stars: int
    title: str
    text: str
    original_text: str | None
    modified: datetime
    reply: str | None


def reviews_path(package: str, month: date) -> str:
    return f"reviews/reviews_{package}_{month:%Y%m}.csv"


def review_id_of(link: str) -> str | None:
    ids = parse_qs(urlparse(link).query).get("reviewId")
    return ids[0] if ids else None


def csv_reviews(raw: bytes) -> list[CsvReview]:
    rows = csv.DictReader(io.StringIO(raw.decode("utf-16")))
    missing = [name for name in REQUIRED_COLUMNS if name not in (rows.fieldnames or [])]
    if missing:
        raise SourceError(f"the reviews file has no '{missing[0]}' column")
    return [
        CsvReview(
            review_id=review_id_of(row["Review Link"]),
            stars=int(row["Star Rating"]),
            title=row["Review Title"],
            text=row["Review Text"],
            language=row["Reviewer Language"],
            submitted=datetime.fromisoformat(row["Review Submit Date and Time"]),
            updated=datetime.fromisoformat(row["Review Last Update Date and Time"]),
            reply=row["Developer Reply Text"] or None,
        )
        for row in rows
    ]


def split_title(text: str) -> tuple[str, str]:
    """The API joins a review's title and body with a tab."""
    title, tab, body = text.partition("\t")
    return (title, body) if tab else ("", text)


def moment_of(timestamp: dict) -> datetime:
    return datetime.fromtimestamp(
        int(timestamp["seconds"]) + timestamp.get("nanos", 0) / 1e9, UTC
    )


def api_review(raw: dict) -> ApiReview:
    comments = raw["comments"]
    user = next(each["userComment"] for each in comments if "userComment" in each)
    developer = next(
        (each["developerComment"] for each in comments if "developerComment" in each),
        None,
    )
    title, text = split_title(user["text"])
    original = user.get("originalText")
    return ApiReview(
        review_id=raw["reviewId"],
        stars=int(user["starRating"]),
        title=title,
        text=text,
        original_text="\n".join(filter(None, split_title(original)))
        if original
        else None,
        modified=moment_of(user["lastModified"]),
        reply=developer["text"] if developer else None,
    )


def all_pages(read_page: PageReader) -> list[dict]:
    """Every review across the API's pages, following `nextPageToken` to the last."""
    found: list[dict] = []
    token = None
    while True:
        page = read_page(token)
        found += page.get("reviews", [])
        token = page.get("tokenPagination", {}).get("nextPageToken")
        if not token:
            return found


def trailing_average(csv_ratings: list[CsvReview], day: date) -> float | None:
    """The average of the ratings of the 28 days ending `day`, or ending on the newest rating
    before it; None when no rating came before."""
    known = [(each.submitted.date(), each.stars) for each in csv_ratings]
    known = [(when, stars) for when, stars in known if when <= day]
    if not known:
        return None
    window = timedelta(days=STORE_RATING_DAYS)
    if not any(when > day - window for when, _ in known):
        day = max(when for when, _ in known)
    stars = [stars for when, stars in known if when > day - window]
    return sum(stars) / len(stars)


def read_csv_reviews(
    read: Reader, package: str, span: Period
) -> tuple[list[CsvReview], list[date]]:
    """The reviews of every monthly file `span` touches, and the months whose file is absent."""
    found: list[CsvReview] = []
    absent: list[date] = []
    for month in span.months():
        raw = read(reviews_path(package, month))
        if raw is None:
            absent.append(month)
        else:
            found += csv_reviews(raw)
    return found, absent


def uncovered_days(
    period: Period, today: date, absent: list[date]
) -> tuple[Period, ...]:
    """The days older than the API's window that fall in a month whose report file is absent."""
    last = min(period.end, today - timedelta(days=API_DAYS))
    missing = []
    for month in absent:
        month_end = (month + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        start, end = max(period.start, month), min(last, month_end)
        if start <= end:
            missing.append(Period(start, end))
    return tuple(missing)


def report_reach(period: Period, today: date, from_csv: list[CsvReview]) -> date:
    """The last day the reviews report is known to cover.

    The report is trusted for days older than the API's window; for newer days it reaches the
    newest day any of its rows names. A report with no rows claims no lag.
    """
    if not from_csv:
        return period.end
    newest = max(max(each.submitted.date(), each.updated.date()) for each in from_csv)
    return max(newest, today - timedelta(days=API_DAYS))


def merged_cards(
    from_csv: list[CsvReview], from_api: list[ApiReview], period: Period
) -> tuple[Review, ...]:
    held = {each.review_id: each for each in from_csv if each.review_id}
    answered = {each.review_id for each in from_api}
    cards = []

    def in_period(moment: datetime) -> bool:
        return period.start <= moment.date() <= period.end

    for each in from_api:
        before = held.get(each.review_id)
        if before is None:
            if in_period(each.modified):
                cards.append(
                    Review(
                        each.stars,
                        each.title,
                        each.text,
                        each.original_text,
                        None,
                        Label.NEW_OR_EDITED,
                        each.modified,
                        each.reply,
                    )
                )
        elif any(map(in_period, (before.submitted, before.updated, each.modified))):
            newest = max(before.updated, each.modified)
            cards.append(
                Review(
                    each.stars,
                    each.title,
                    each.text,
                    each.original_text,
                    None,
                    Label.NEW if in_period(before.submitted) else Label.EDITED,
                    newest,
                    each.reply,
                )
            )
    for each in from_csv:
        if each.review_id in answered or not each.has_text:
            continue
        if in_period(each.submitted) or in_period(each.updated):
            new = in_period(each.submitted)
            cards.append(
                Review(
                    each.stars,
                    each.title,
                    each.text,
                    None,
                    each.language,
                    Label.NEW if new else Label.EDITED,
                    each.submitted if new else each.updated,
                    each.reply,
                )
            )
    return tuple(sorted(cards, key=lambda card: card.at, reverse=True))


def reviews(
    read: Reader,
    list_reviews: ApiReader,
    package: str,
    today: date,
    period: Period | None = None,
) -> Reviews | Unavailable:
    """Ratings and reviews for `period`, or for the week that just ended."""
    read = memoized(read)
    period = period or week_ending_by(today - timedelta(days=1))
    window = timedelta(days=STORE_RATING_DAYS - 1)
    from_csv, absent = read_csv_reviews(
        read, package, Period(period.trend_start() - window, period.end)
    )
    uncovered = uncovered_days(period, today, absent)
    coverage = reached(SOURCE, period, report_reach(period, today, from_csv))
    if (
        isinstance(coverage, Unavailable)
        or sum(gap.length for gap in uncovered) >= period.length
    ):
        return Unavailable(SOURCE, period)
    api_reaches = period.end >= today - timedelta(days=API_DAYS)
    from_api = [api_review(raw) for raw in list_reviews()] if api_reaches else []

    def daily(value: Callable[[CsvReview], float]) -> dict[date, float]:
        totals: dict[date, float] = {}
        for each in from_csv:
            day = each.submitted.date()
            totals[day] = totals.get(day, 0) + value(each)
        return totals

    count = Metric.summed(daily(lambda each: 1), coverage)
    stars = Metric.summed(daily(lambda each: each.stars), coverage)
    return Reviews(
        coverage=coverage,
        store_rating=Metric.level(
            lambda day: trailing_average(from_csv, day), coverage
        ),
        new_ratings=count,
        new_average=Metric.ratio(stars, count, per=1),
        breakdown={
            level: sum(
                1
                for each in from_csv
                if each.stars == level
                and period.start <= each.submitted.date() <= period.end
            )
            for level in STAR_LEVELS
        },
        reviews=merged_cards(from_csv, from_api, period),
        uncovered=uncovered,
    )


def api_reader(app: AppConfig) -> ApiReader:
    client = build(
        "androidpublisher",
        "v3",
        credentials=service_account_credentials(app, SCOPE),
    )

    def read_page(token: str | None) -> dict:
        return (
            client.reviews()
            .list(
                packageName=app.package,
                maxResults=100,
                token=token,
                translationLanguage=TRANSLATION_LANGUAGE,
            )
            .execute()
        )

    return lambda: all_pages(read_page)
