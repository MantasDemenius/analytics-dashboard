"""Renders a full report from made-up data to out/sample/, as HTML and as the printed PDF.

Every section ticket adds its section here, so the layout can be checked by eye without real
data. Covers a rise, a fall and no change, a section with data ending inside its range, a failed
source and a range a source cannot reach. The reviews cover every label, a translation, a review
only the report holds, a reply, a run too late for part of the range and a week with no ratings.

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
    Label,
    Listing,
    Metric,
    Report,
    Review,
    Reviews,
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


def rating_wave(day: date) -> float:
    return 3.7 + 0.3 * math.sin(day.toordinal() / 17)


def reviews_section(
    new_ratings: dict[date, float],
    average: float,
    cards: tuple[Review, ...] = (),
    breakdown: dict[int, int] | None = None,
    uncovered: tuple[Period, ...] = (),
) -> Reviews:
    coverage = Coverage(REPORT_WEEK)
    stars = {day: count * average for day, count in new_ratings.items()}
    count = Metric.summed(new_ratings, coverage)
    return Reviews(
        coverage,
        store_rating=Metric.level(rating_wave, coverage),
        new_ratings=count,
        new_average=Metric.ratio(Metric.summed(stars, coverage), count, per=1),
        breakdown=breakdown or {5: 0, 4: 0, 3: 0, 2: 0, 1: 0},
        reviews=cards,
        uncovered=uncovered,
    )


def card(
    stars: int,
    text: str,
    day: int,
    label: Label = Label.NEW,
    title: str = "",
    original_text: str | None = None,
    language: str | None = None,
    reply: str | None = None,
) -> Review:
    return Review(
        stars,
        title,
        text,
        original_text,
        language,
        label,
        datetime(2026, 10, day, 14, 30),
        reply,
    )


EXAMPLE_REVIEWS = (
    card(
        5,
        "Exactly what I needed. The widgets are quick and the dark theme is easy on the eyes.",
        31,
        title="Exactly what I needed",
        reply="Thank you, we are glad it helps. More widgets are on the way.",
    ),
    card(1, "Crashes every time I open it after the update.", 30, title="Broken"),
    card(
        4,
        "Was missing a search before, the new version fixed that. Still wish it synced between my devices.",
        30,
        Label.EDITED,
    ),
    card(
        5,
        "Very easy to use, the widgets are great.\nI use them every day.",
        29,
        Label.NEW_OR_EDITED,
        title="Great",
        original_text="Super\nSehr einfach zu bedienen, die Widgets sind toll.\nIch nutze sie jeden Tag.",
    ),
    card(
        3,
        "Bom, mas poderia ter mais opções.",
        28,
        language="pt",
        reply="Obrigado pelo comentário!",
    ),
    card(2, "", 27, title="Too many ads"),
    card(
        4,
        "A very long review without a single line break, written by someone who wanted to explain "
        "every detail of how they use the app on their commute, at home, at work and on holiday, "
        "including a complaint about the notification sound that cannot be changed. "
        * 2,
        26,
    ),
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
                reviews_section(
                    swinging(REPORT_WEEK, 4, 0.01, 5),
                    4.2,
                    EXAMPLE_REVIEWS,
                    {5: 14, 4: 9, 3: 5, 2: 2, 1: 3},
                ),
            ),
            AppReport(
                "Second App",
                growth(
                    swinging(BUCKET_WEEK, 60, 0.1, 40),
                    swinging(BUCKET_WEEK, 45, 0.05, 70),
                    data_to=date(2026, 10, 22),
                ),
                listing(listing_visitors(300), rate=0.18, data_to=date(2026, 10, 15)),
                reviews_section(
                    swinging(REPORT_WEEK, 2, 0.01, 2),
                    3.1,
                    EXAMPLE_REVIEWS[1:3],
                    {5: 1, 4: 2, 3: 3, 2: 4, 1: 4},
                    uncovered=(Period(date(2026, 10, 26), date(2026, 10, 27)),),
                ),
            ),
            AppReport(
                "Third App",
                growth(flat_week(), swinging(BUCKET_WEEK, 20, 0.02, 20)),
                listing(listing_visitors(380), rate=0.2),
                reviews_section({}, 0),
            ),
            AppReport(
                "Fourth App",
                Failure("Play report bucket", "403 Forbidden"),
                Failure("Play report bucket", "403 Forbidden"),
                Failure("Play reviews", "403 Forbidden"),
            ),
            AppReport(
                "Fifth App",
                Unavailable("Play report bucket", BUCKET_WEEK),
                Unavailable("Play report bucket", LISTING_WEEK),
                Unavailable("Play reviews", REPORT_WEEK),
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
