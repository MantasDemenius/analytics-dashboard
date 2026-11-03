import contextlib
import io
import unittest
from datetime import date

from weekly_report.__main__ import attempt, build_report, parse_args, requested_range
from weekly_report.model import Failure
from weekly_report.periods import Period


def outage():
    raise RuntimeError("503 Service Unavailable")


class AttemptTest(unittest.TestCase):
    def test_a_working_source_gives_its_section(self):
        self.assertEqual(attempt("Source", lambda: 42), 42)

    def test_a_failing_source_becomes_a_failure_naming_it(self):
        with self.assertLogs("weekly_report", level="ERROR"):
            result = attempt("Source", outage)
        self.assertEqual(result, Failure("Source", "503 Service Unavailable"))

    def test_an_error_without_a_message_is_named_by_its_type(self):
        def empty():
            raise KeyError()

        with self.assertLogs("weekly_report", level="ERROR"):
            result = attempt("Source", empty)
        self.assertEqual(result, Failure("Source", "KeyError"))


class ParseArgsTest(unittest.TestCase):
    def test_by_hand_it_opens_and_does_not_email(self):
        args = parse_args([])
        self.assertFalse(args.email)
        self.assertFalse(args.no_open)

    def test_the_unattended_flags(self):
        args = parse_args(["--email", "--no-open"])
        self.assertTrue(args.email)
        self.assertTrue(args.no_open)

    def test_dates_default_to_none(self):
        args = parse_args([])
        self.assertIsNone(args.from_date)
        self.assertIsNone(args.to_date)

    def test_a_range_is_read_as_inclusive_dates(self):
        args = parse_args(["--from", "2026-10-20", "--to", "2026-11-02"])
        self.assertEqual(args.from_date, date(2026, 10, 20))
        self.assertEqual(args.to_date, date(2026, 11, 2))

    def refused(self, argv: list[str]) -> str:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as exit_:
            parse_args(argv)
        self.assertEqual(exit_.exception.code, 2)
        return stderr.getvalue()

    def test_from_alone_is_refused(self):
        self.assertIn("--from and --to", self.refused(["--from", "2026-10-20"]))

    def test_to_alone_is_refused(self):
        self.assertIn("--from and --to", self.refused(["--to", "2026-10-20"]))

    def test_a_range_ending_before_it_starts_is_refused(self):
        self.assertIn(
            "before", self.refused(["--from", "2026-11-02", "--to", "2026-11-01"])
        )

    def test_a_malformed_date_is_refused(self):
        self.assertIn(
            "YYYY-MM-DD", self.refused(["--from", "20/10", "--to", "2026-11-01"])
        )


class RequestedRangeTest(unittest.TestCase):
    def test_without_dates_sources_pick_their_own_weeks(self):
        self.assertIsNone(requested_range(parse_args([])))

    def test_with_dates_it_is_that_range(self):
        args = parse_args(["--from", "2026-10-20", "--to", "2026-11-02"])
        self.assertEqual(
            requested_range(args), Period(date(2026, 10, 20), date(2026, 11, 2))
        )


class BuildReportTest(unittest.TestCase):
    def test_the_report_period_is_the_week_that_just_ended_by_default(self):
        report = build_report([], date(2026, 11, 3), "pub-0")
        self.assertEqual(report.period, Period(date(2026, 10, 26), date(2026, 11, 1)))

    def test_the_report_period_is_the_requested_range(self):
        requested = Period(date(2026, 10, 20), date(2026, 11, 2))
        report = build_report([], date(2026, 11, 3), "pub-0", requested)
        self.assertEqual(report.period, requested)


if __name__ == "__main__":
    unittest.main()
