"""Renders a full report from made-up data to out/sample/, as HTML and as the printed PDF.

Every section ticket adds its section here, so the layout can be checked by eye without real
data. Covers a rise, a fall and no change, a section with data ending inside its range, a failed
source and a range a source cannot reach.

Run: uv run python scripts/render_sample.py
"""

import math
from datetime import date, datetime, timedelta
from pathlib import Path

from weekly_report import pdf
from weekly_report.model import (
    AppReport,
    Failure,
    Growth,
    Listing,
    Metric,
    Report,
    Unavailable,
)
from weekly_report.periods import TREND_PERIODS, Coverage, Period
from weekly_report.render import render, write

OUT_DIR = Path("out/sample")
REPORT_WEEK = Period(date(2026, 10, 26), date(2026, 11, 1))
BUCKET_WEEK = REPORT_WEEK.previous()
LISTING_WEEK = BUCKET_WEEK.previous()


def swinging(
    period: Period, base: float, slope: float, this_week: float
) -> dict[date, float]:
    """Made-up counts per day: a gentle trend with a slow swing, then `this_week` per day."""
    first = period.trailing(TREND_PERIODS)[0].start
    daily = {}
    for offset in range((period.start - first).days):
        day = first + timedelta(days=offset)
        swing = 1 + 0.12 * math.sin(offset / 9) + 0.2 * math.sin(offset * 2.1)
        daily[day] = round((base + slope * offset) * swing)
    for offset, day in enumerate(period.days()):
        daily[day] = round(this_week * (0.85 + 0.05 * offset))
    return daily


def growth(
    installs: dict[date, float],
    uninstalls: dict[date, float],
    data_to: date | None = None,
) -> Growth:
    coverage = Coverage(BUCKET_WEEK, data_to)
    net = {day: installs.get(day, 0) - uninstalls.get(day, 0) for day in installs}
    return Growth(
        coverage,
        installs=Metric.summed(installs, coverage),
        uninstalls=Metric.summed(uninstalls, coverage),
        net=Metric.summed(net, coverage),
    )


def listing(
    visitors: dict[date, float], rate: float, data_to: date | None = None
) -> Listing:
    coverage = Coverage(LISTING_WEEK, data_to)
    acquisitions = {day: round(count * rate) for day, count in visitors.items()}
    visited = Metric.summed(visitors, coverage)
    acquired = Metric.summed(acquisitions, coverage)
    return Listing(
        coverage,
        visitors=visited,
        acquisitions=acquired,
        conversion=Metric.ratio(acquired, visited),
    )


def flat_week() -> dict[date, float]:
    daily = swinging(BUCKET_WEEK, base=30, slope=0.05, this_week=34)
    previous = BUCKET_WEEK.previous().days()
    total = sum(daily[day] for day in BUCKET_WEEK.days())
    for day in previous:
        daily[day] = 0
    daily[previous[0]] = total
    return daily


def listing_visitors(this_week: float) -> dict[date, float]:
    return swinging(LISTING_WEEK, base=380, slope=0.2, this_week=this_week)


def sample() -> Report:
    return Report(
        period=REPORT_WEEK,
        generated=datetime(2026, 11, 2, 8, 0),
        apps=(
            AppReport(
                "Example App",
                growth(
                    swinging(BUCKET_WEEK, 120, 0.3, 190),
                    swinging(BUCKET_WEEK, 40, 0.1, 45),
                ),
                listing(listing_visitors(520), rate=0.31),
            ),
            AppReport(
                "Second App",
                growth(
                    swinging(BUCKET_WEEK, 60, 0.1, 40),
                    swinging(BUCKET_WEEK, 45, 0.05, 70),
                    data_to=date(2026, 10, 22),
                ),
                listing(listing_visitors(300), rate=0.18, data_to=date(2026, 10, 15)),
            ),
            AppReport(
                "Third App",
                growth(flat_week(), swinging(BUCKET_WEEK, 20, 0.02, 20)),
                listing(listing_visitors(380), rate=0.2),
            ),
            AppReport(
                "Fourth App",
                Failure("Play report bucket", "403 Forbidden"),
                Failure("Play report bucket", "403 Forbidden"),
            ),
            AppReport(
                "Fifth App",
                Unavailable("Play report bucket", BUCKET_WEEK),
                Unavailable("Play report bucket", LISTING_WEEK),
            ),
        ),
    )


def main() -> None:
    report = sample()
    html = write(render(report), OUT_DIR)
    pages = pdf.print_pdf(
        pdf.find_chrome(None), html, OUT_DIR / "report.pdf", len(report.apps)
    )
    print(f"HTML: {html}\nPDF:  {OUT_DIR / 'report.pdf'} ({pages} pages)")


if __name__ == "__main__":
    main()
