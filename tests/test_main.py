import unittest

from weekly_report.__main__ import attempt, parse_args
from weekly_report.model import Failure


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


if __name__ == "__main__":
    unittest.main()
