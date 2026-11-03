"""Date ranges the report covers. Every range is inclusive at both ends."""

from dataclasses import dataclass
from datetime import date, timedelta

SUNDAY = 6


@dataclass(frozen=True)
class Period:
    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(f"period ends {self.end} before it starts {self.start}")

    @property
    def length(self) -> int:
        return (self.end - self.start).days + 1

    def days(self) -> list[date]:
        return [self.start + timedelta(days=offset) for offset in range(self.length)]

    def previous(self) -> Period:
        """The period of the same length that ends the day before this one starts."""
        end = self.start - timedelta(days=1)
        return Period(end - timedelta(days=self.length - 1), end)

    def months(self) -> list[date]:
        """The first day of every calendar month the period touches, in order."""
        months = []
        month = self.start.replace(day=1)
        while month <= self.end:
            months.append(month)
            month = (month + timedelta(days=32)).replace(day=1)
        return months

    def label(self) -> str:
        end = f"{self.end.day} {self.end:%b %Y}"
        if self.start.year == self.end.year:
            return f"{self.start.day} {self.start:%b} to {end}"
        return f"{self.start.day} {self.start:%b %Y} to {end}"


def week_ending_by(last_day: date) -> Period:
    """The newest Monday to Sunday week that ends on or before `last_day`."""
    end = last_day - timedelta(days=(last_day.weekday() - SUNDAY) % 7)
    return Period(end - timedelta(days=6), end)
