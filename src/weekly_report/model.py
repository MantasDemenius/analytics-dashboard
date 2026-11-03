"""Plain data the sources produce and the template reads."""

from dataclasses import dataclass, field, fields
from datetime import date, datetime

from weekly_report.periods import Period


@dataclass(frozen=True)
class Point:
    day: date
    value: float


@dataclass(frozen=True)
class Metric:
    """A number for a period, the same number for the period before, and its daily points."""

    value: float
    previous: float
    series: tuple[Point, ...] = ()

    @property
    def change(self) -> float:
        return self.value - self.previous

    @property
    def percent_change(self) -> float | None:
        if self.previous == 0:
            return None
        return self.change / self.previous * 100


@dataclass(frozen=True)
class Failure:
    """A section whose source failed; the report shows the error in its place."""

    source: str
    error: str


@dataclass(frozen=True)
class Growth:
    period: Period
    installs: Metric


@dataclass(frozen=True)
class AppReport:
    """One app's sections. Every field after `app` is a section or the Failure that replaced it."""

    app: str
    growth: Growth | Failure

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
