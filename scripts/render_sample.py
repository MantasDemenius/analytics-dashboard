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
from weekly_report.model import AppReport, Failure, Growth, Metric, Report, Unavailable
from weekly_report.periods import TREND_PERIODS, Coverage, Period
from weekly_report.render import render, write

OUT_DIR = Path("out/sample")
REPORT_WEEK = Period(date(2026, 10, 26), date(2026, 11, 1))
BUCKET_WEEK = REPORT_WEEK.previous()


def daily_installs(base: float, slope: float, this_week: float) -> dict[date, float]:
    """Made-up installs per day: a gentle trend with a slow swing, then `this_week` per day."""
    first = BUCKET_WEEK.trailing(TREND_PERIODS)[0].start
    daily = {}
    for offset in range((BUCKET_WEEK.start - first).days):
        day = first + timedelta(days=offset)
        swing = 1 + 0.12 * math.sin(offset / 9) + 0.2 * math.sin(offset * 2.1)
        daily[day] = round((base + slope * offset) * swing)
    for offset, day in enumerate(BUCKET_WEEK.days()):
        daily[day] = round(this_week * (0.85 + 0.05 * offset))
    return daily


def growth(daily: dict[date, float], data_to: date | None = None) -> Growth:
    coverage = Coverage(BUCKET_WEEK, data_to)
    return Growth(coverage, Metric.summed(daily, coverage))


def flat_week() -> dict[date, float]:
    daily = daily_installs(base=30, slope=0.05, this_week=34)
    previous = BUCKET_WEEK.previous().days()
    total = sum(daily[day] for day in BUCKET_WEEK.days())
    for day in previous:
        daily[day] = 0
    daily[previous[0]] = total
    return daily


def sample() -> Report:
    return Report(
        period=REPORT_WEEK,
        generated=datetime(2026, 11, 2, 8, 0),
        apps=(
            AppReport("Example App", growth(daily_installs(120, 0.3, 190))),
            AppReport(
                "Second App",
                growth(daily_installs(60, 0.1, 40), data_to=date(2026, 10, 22)),
            ),
            AppReport("Third App", growth(flat_week())),
            AppReport("Fourth App", Failure("Play report bucket", "403 Forbidden")),
            AppReport("Fifth App", Unavailable("Play report bucket", BUCKET_WEEK)),
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
