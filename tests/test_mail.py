import unittest
from datetime import date, datetime

from weekly_report.mail import message, subject
from weekly_report.model import AppReport, Growth, Listing, Metric, Report
from weekly_report.periods import Coverage, Period

WEEK = Period(date(2026, 10, 26), date(2026, 11, 1))
GROWTH_WEEK = Period(date(2026, 10, 19), date(2026, 10, 25))
LISTING_WEEK = Period(date(2026, 10, 12), date(2026, 10, 18))
REPORT = Report(
    period=WEEK,
    apps=(
        AppReport(
            "first",
            Growth(
                Coverage(GROWTH_WEEK),
                installs=Metric(80, 60),
                uninstalls=Metric(11, 8),
                net=Metric(69, 52),
            ),
            Listing(
                Coverage(LISTING_WEEK),
                visitors=Metric(400, 380),
                acquisitions=Metric(50, 38),
                conversion=Metric(12.5, 10.0),
            ),
        ),
    ),
    generated=datetime(2026, 11, 2, 8, 0),
)


class SubjectTest(unittest.TestCase):
    def test_names_the_range(self):
        self.assertEqual(subject(WEEK), "Weekly app report, 26 Oct to 1 Nov 2026")


class MessageTest(unittest.TestCase):
    def setUp(self):
        self.message = message("author@example.com", REPORT, b"%PDF-1.4 made up")

    def test_is_addressed_to_the_recipient_with_the_subject(self):
        self.assertEqual(self.message["To"], "author@example.com")
        self.assertEqual(
            self.message["Subject"], "Weekly app report, 26 Oct to 1 Nov 2026"
        )

    def test_the_body_is_plain_text_with_the_period_and_net_growth(self):
        body = self.message.get_body(("plain",)).get_content()
        self.assertIn("26 Oct to 1 Nov 2026", body)
        self.assertIn(
            "Net growth, 19 Oct to 25 Oct 2026: +69, +17 (+32.7%), better", body
        )

    def test_attaches_the_pdf(self):
        [attachment] = list(self.message.iter_attachments())
        self.assertEqual(attachment.get_content_type(), "application/pdf")
        self.assertEqual(
            attachment.get_filename(), "weekly-app-report-2026-10-26-to-2026-11-01.pdf"
        )
        self.assertEqual(attachment.get_content(), b"%PDF-1.4 made up")


if __name__ == "__main__":
    unittest.main()
