"""How the report writes its numbers: values, signed changes and the texts that stand in."""

from dataclasses import dataclass
from datetime import date

from weekly_report.model import Metric

MINUS = "−"
NOT_AVAILABLE = "not available for this range"
NONE = "none"
NO_COMPARISON = "no ratings to compare"
NOTHING_TO_COMPARE = "nothing to compare"
NO_CHANGE = "no change"


def signed(number: float, digits: int = 0, unit: str = "") -> str:
    rounded = round(number, digits)
    text = f"{abs(rounded):,.{digits}f}{unit}"
    if rounded > 0:
        return f"+{text}"
    if rounded < 0:
        return f"{MINUS}{text}"
    return text


def count(number: float) -> str:
    return f"{number:,.0f}"


def before(days: int) -> str:
    if days == 7:
        return "the week before"
    if days == 1:
        return "the day before"
    return f"the {days} days before"


def periods_of(days: int) -> str:
    if days == 7:
        return "weeks"
    if days == 1:
        return "days"
    return f"periods of {days} days"


def short_day(day: date) -> str:
    return f"{day.day} {day:%b}"


def percent(number: float) -> str:
    return f"{number:.1f}%"


def rate(number: float) -> str:
    return f"{number:.2f}%"


def crash_free(number: float) -> str:
    return rate(number) if number else NONE


def rating(number: float) -> str:
    return f"{number:.2f}" if number else NONE


def money(number: float) -> str:
    return f"{number:,.2f}"


@dataclass(frozen=True)
class Change:
    """How a change is written: rounded to `digits` with `unit` after it, and with its percent
    when `percent` is set. A change that rounds to zero is "no change", whatever its size
    before rounding. `unknown` is what stands in when the two values cannot be compared."""

    digits: int = 0
    unit: str = ""
    percent: bool = False
    unknown: str = NOTHING_TO_COMPARE

    def rounded(self, metric: Metric) -> float:
        return round(metric.change, self.digits)

    def text(self, metric: Metric) -> str:
        if self.rounded(metric) == 0:
            return NO_CHANGE
        change = signed(metric.change, self.digits, self.unit)
        if not self.percent or metric.percent_change is None:
            return change
        return f"{change} ({signed(metric.percent_change, 1, '%')})"


WHOLE_PERCENT_CHANGE = Change(percent=True)
