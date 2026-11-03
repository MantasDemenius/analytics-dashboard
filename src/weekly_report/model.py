"""Plain data the sources produce and the template reads."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, fields
from datetime import date, datetime

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
    def ratio(cls, part: Metric, whole: Metric) -> Metric:
        """`part` as a percent of `whole`, from their sums, never an average of daily ratios."""

        def percent(numerator: float, denominator: float) -> float:
            return numerator / denominator * 100 if denominator else 0.0

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


@dataclass(frozen=True)
class AppReport:
    """One app's sections. Every field after `app` is a section or the Failure that replaced it."""

    app: str
    growth: Growth | Unavailable | Failure
    listing: Listing | Unavailable | Failure

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
