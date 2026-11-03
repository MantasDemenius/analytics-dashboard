"""Builds the weekly report for every app config, opens it, and with --email prints and mails it.

Prints only the period, counts, problems and file paths, never review or feedback text.
Exits non-zero when a source fails or the PDF or email cannot be made.
"""

import argparse
import logging
import sys
import webbrowser
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

from weekly_report import mail, pdf
from weekly_report.config import AppConfig, ConfigError, load_apps, load_report
from weekly_report.model import (
    AdMob,
    AppReport,
    Crashlytics,
    Failure,
    Feedback,
    Report,
    Reviews,
    Unavailable,
    Vitals,
)
from weekly_report.periods import Period, week_ending_by
from weekly_report.render import render, summary, write
from weekly_report.sources import (
    admob,
    crashlytics,
    feedback,
    play_bucket,
    play_reviews,
    play_vitals,
)

OUT_DIR = Path("out")
PDF_PATH = OUT_DIR / "report.pdf"
LOG_FILE = Path("logs/weekly-report.log")

log = logging.getLogger("weekly_report")


def iso_date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got '{text}'") from None


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="weekly-report", description=__doc__)
    parser.add_argument(
        "--from",
        dest="from_date",
        type=iso_date,
        metavar="YYYY-MM-DD",
        help="first day of the range, inclusive; needs --to",
    )
    parser.add_argument(
        "--to",
        dest="to_date",
        type=iso_date,
        metavar="YYYY-MM-DD",
        help="last day of the range, inclusive; needs --from",
    )
    parser.add_argument(
        "--email", action="store_true", help="print the PDF and email it"
    )
    parser.add_argument(
        "--no-open", action="store_true", help="do not open the report in a browser"
    )
    args = parser.parse_args(argv)
    if (args.from_date is None) != (args.to_date is None):
        parser.error("--from and --to go together")
    if args.from_date and args.to_date < args.from_date:
        parser.error(f"--to {args.to_date} is before --from {args.from_date}")
    return args


def requested_range(args: argparse.Namespace) -> Period | None:
    if args.from_date is None:
        return None
    return Period(args.from_date, args.to_date)


def attempt[T](source: str, build: Callable[[], T]) -> T | Failure:
    """Runs one source; a failure replaces its section instead of stopping the report."""
    try:
        return build()
    except Exception as error:
        log.exception("%s failed", source)
        return Failure(source, str(error) or type(error).__name__)


def from_bucket[T](
    app: AppConfig,
    today: date,
    period: Period | None,
    section: Callable[[play_bucket.Reader, str, date, Period | None], T],
) -> T | Failure:
    return attempt(
        play_bucket.SOURCE,
        lambda: section(play_bucket.bucket_reader(app), app.package, today, period),
    )


def from_play_reviews(
    app: AppConfig, today: date, period: Period | None
) -> Reviews | Unavailable | Failure:
    return attempt(
        play_reviews.SOURCE,
        lambda: play_reviews.reviews(
            play_bucket.bucket_reader(app),
            play_reviews.api_reader(app),
            app.package,
            today,
            period,
        ),
    )


def from_play_vitals(
    app: AppConfig, period: Period | None
) -> Vitals | Unavailable | Failure:
    return attempt(
        play_vitals.SOURCE,
        lambda: play_vitals.vitals(*play_vitals.readers(app), period),
    )


def from_crashlytics(
    app: AppConfig, today: date, period: Period | None
) -> Crashlytics | Unavailable | Failure:
    return attempt(
        crashlytics.SOURCE,
        lambda: crashlytics.crashlytics(crashlytics.reader(app), today, period),
    )


def from_feedback(
    app: AppConfig, today: date, period: Period | None
) -> Feedback | Unavailable | Failure:
    return attempt(
        feedback.SOURCE,
        lambda: feedback.feedback(*feedback.readers(app), today, period),
    )


def from_admob(
    publisher: str, today: date, period: Period | None
) -> AdMob | Unavailable | Failure:
    return attempt(
        admob.SOURCE, lambda: admob.admob(admob.reader(publisher), today, period)
    )


def app_report(
    app: AppConfig,
    today: date,
    period: Period | None,
    ads: AdMob | Unavailable | Failure,
) -> AppReport:
    return AppReport(
        app=app.name,
        growth=from_bucket(app, today, period, play_bucket.growth),
        listing=from_bucket(app, today, period, play_bucket.listing),
        reviews=from_play_reviews(app, today, period),
        vitals=from_play_vitals(app, period),
        crashlytics=from_crashlytics(app, today, period),
        feedback=from_feedback(app, today, period),
        admob=ads,
    )


def build_report(
    apps: list[AppConfig],
    today: date,
    admob_publisher: str,
    requested: Period | None = None,
) -> Report:
    """With no `requested` range every source picks its own newest complete week.

    The AdMob account is one for all apps, so it is read once and every app shows it.
    """
    period = requested or week_ending_by(today - timedelta(days=1))
    if not apps:
        return Report(period, ())
    ads = from_admob(admob_publisher, today, requested)
    return Report(period, tuple(app_report(app, today, requested, ads) for app in apps))


def email_report(report: Report, html: Path, chrome: Path | None, to: str) -> bool:
    try:
        pages = pdf.print_pdf(
            pdf.find_chrome(chrome), html, PDF_PATH, min_pages=len(report.apps)
        )
    except Exception as error:
        log.exception("printing the PDF failed")
        print(f"PDF failed: {error} (see {LOG_FILE})")
        return False
    print(f"PDF:  {PDF_PATH} ({pages} page{'' if pages == 1 else 's'})")
    try:
        mail.send(mail.message(to, report, PDF_PATH.read_bytes()))
    except Exception as error:
        log.exception("sending the email failed")
        print(f"Email failed: {error} (see {LOG_FILE})")
        return False
    print("Email sent")
    return True


def use_utf8_output() -> None:
    """Makes stdout and stderr UTF-8 whatever they are redirected to."""
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    use_utf8_output()
    args = parse_args(sys.argv[1:] if argv is None else argv)
    LOG_FILE.parent.mkdir(exist_ok=True)
    logging.basicConfig(
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8", delay=True)],
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        report_config = load_report()
        apps = load_apps()
    except ConfigError as error:
        sys.exit(str(error))

    report = build_report(
        apps, date.today(), report_config.admob_publisher, requested_range(args)
    )
    PDF_PATH.unlink(missing_ok=True)
    html = write(render(report), OUT_DIR)
    print("\n".join(summary(report)))
    print(f"\nHTML: {html}")
    if not args.no_open:
        webbrowser.open(html.resolve().as_uri())

    emailed = not args.email or email_report(
        report, html, report_config.chrome, report_config.recipient
    )
    sys.exit(0 if emailed and not report.problems else 1)


if __name__ == "__main__":
    main()
