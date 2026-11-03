"""Plain data the sources produce and the template reads."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, fields
from datetime import date, datetime
from enum import Enum

from weekly_report.periods import TREND_PERIODS, Coverage, Period


@dataclass(frozen=True)
class Point:
    day: date
    value: float


@dataclass(frozen=True)
class Metric:
    """A number for a range and for the range before cut to the same days.

    `series` holds the covered days; `trend` holds the same measure for 12 periods of the
    range's length, oldest first, each dated by the day its period starts.
    """

    value: float
    previous: float
    series: tuple[Point, ...] = ()
    trend: tuple[Point, ...] = ()

    @classmethod
    def summed(cls, daily: dict[date, float], coverage: Coverage) -> Metric:
        """Totals of `daily`, a missing day counting as zero."""
        covered = coverage.covered
        days = covered.length

        def total(period: Period) -> float:
            return sum(daily.get(day, 0) for day in period.cut(days).days())

        return cls(
            value=total(coverage.period),
            previous=total(coverage.period.previous()),
            series=tuple(Point(day, daily.get(day, 0)) for day in covered.days()),
            trend=tuple(
                Point(period.start, total(period))
                for period in coverage.period.trailing(TREND_PERIODS)
            ),
        )

    @classmethod
    def level(cls, level_on: Callable[[date], float], coverage: Coverage) -> Metric:
        """The level on the last covered day, one period earlier, and at each period's end."""
        period = coverage.period
        days = coverage.covered.length

        def at_end(of: Period) -> float:
            return level_on(of.cut(days).end)

        return cls(
            value=at_end(period),
            previous=at_end(period.previous()),
            trend=tuple(
                Point(each.start, at_end(each))
                for each in period.trailing(TREND_PERIODS)
            ),
        )

    @classmethod
    def ratio(cls, part: Metric, whole: Metric, per: float = 100) -> Metric:
        """`part` per `per` of `whole` (a percent by default), from their sums, never an average of daily ratios."""

        def percent(numerator: float, denominator: float) -> float:
            return numerator / denominator * per if denominator else 0.0

        return cls(
            value=percent(part.value, whole.value),
            previous=percent(part.previous, whole.previous),
            trend=tuple(
                Point(each.day, percent(each.value, total.value))
                for each, total in zip(part.trend, whole.trend, strict=True)
            ),
        )

    @property
    def change(self) -> float:
        return self.value - self.previous

    @property
    def percent_change(self) -> float | None:
        if self.previous == 0:
            return None
        return self.change / abs(self.previous) * 100


@dataclass(frozen=True)
class Failure:
    """A section whose source failed; the report shows the error in its place."""

    source: str
    error: str


@dataclass(frozen=True)
class Unavailable:
    """A section whose source holds nothing for the range; shown as such, not a problem."""

    source: str
    period: Period


@dataclass(frozen=True)
class Growth:
    coverage: Coverage
    installs: Metric
    uninstalls: Metric
    net: Metric


@dataclass(frozen=True)
class Listing:
    coverage: Coverage
    visitors: Metric
    acquisitions: Metric
    conversion: Metric


class Label(Enum):
    NEW = "new"
    EDITED = "edited"
    NEW_OR_EDITED = "new or edited"


@dataclass(frozen=True)
class Review:
    """One review card. `text` is the English translation when there is one, shown above
    `original_text`; `language` is set only on a review the Reviews API did not return."""

    stars: int
    title: str
    text: str
    original_text: str | None
    language: str | None
    label: Label
    at: datetime
    reply: str | None

    @property
    def replied(self) -> bool:
        return self.reply is not None


@dataclass(frozen=True)
class Reviews:
    """The ratings and reviews of a range.

    `store_rating` is the 28 day average rating as of each period's last day. `uncovered`
    holds the days neither the Reviews API nor the reviews report can account for.
    """

    coverage: Coverage
    store_rating: Metric
    new_ratings: Metric
    new_average: Metric
    breakdown: dict[int, int]
    reviews: tuple[Review, ...]
    uncovered: tuple[Period, ...] = ()


CRASH_THRESHOLD = 1.09
ANR_THRESHOLD = 0.47


@dataclass(frozen=True)
class Vitals:
    """User-perceived crash and ANR rate as 28 day user weighted percents, each a level.

    Play's bad behaviour thresholds for them are `CRASH_THRESHOLD` and `ANR_THRESHOLD`.
    """

    coverage: Coverage
    crash_rate: Metric
    anr_rate: Metric


class Signal(Enum):
    """What Crashlytics' analyzer says about an issue; the order is the order a card shows them."""

    FRESH = "New"
    REGRESSED = "Regressed"
    EARLY = "Early"
    REPETITIVE = "Repetitive"


class ErrorKind(Enum):
    FATAL = "Crash"
    NON_FATAL = "Non-fatal"
    ANR = "ANR"


class IssueState(Enum):
    OPEN = "Open"
    CLOSED = "Closed"
    MUTED = "Muted"


@dataclass(frozen=True)
class Issue:
    """One Crashlytics issue, its counts being those of the range."""

    title: str
    subtitle: str
    kind: ErrorKind
    state: IssueState
    signals: tuple[Signal, ...]
    users: int
    events: int
    first_seen_version: str | None
    link: str | None

    @property
    def needs_attention(self) -> bool:
        return Signal.FRESH in self.signals or Signal.REGRESSED in self.signals


@dataclass(frozen=True)
class Crashlytics:
    """Crash free users over the range and every issue, new and regressed first.

    `crash_free` is a percent of the range's users; 0 means Crashlytics counted none, and a
    `previous` of 0 means the range before it lies past the 90 days Crashlytics keeps.
    """

    coverage: Coverage
    crash_free: Metric
    issues: tuple[Issue, ...]


@dataclass(frozen=True)
class AppReport:
    """One app's sections. Every field after `app` is a section or the Failure that replaced it."""

    app: str
    growth: Growth | Unavailable | Failure
    listing: Listing | Unavailable | Failure
    reviews: Reviews | Unavailable | Failure
    vitals: Vitals | Unavailable | Failure
    crashlytics: Crashlytics | Unavailable | Failure

    def failures(self) -> list[Failure]:
        sections = (getattr(self, f.name) for f in fields(self) if f.name != "app")
        return [section for section in sections if isinstance(section, Failure)]


@dataclass(frozen=True)
class Report:
    period: Period
    apps: tuple[AppReport, ...]
    generated: datetime = field(default_factory=datetime.now)

    @property
    def problems(self) -> list[tuple[str, Failure]]:
        return [(app.app, failure) for app in self.apps for failure in app.failures()]
