import unittest
from datetime import date

from weekly_report.model import Unavailable
from weekly_report.periods import Coverage, Period
from weekly_report.sources.shared import reached

WEEK = Period(date(2026, 10, 26), date(2026, 11, 1))


class ReachedTest(unittest.TestCase):
    def test_a_requested_period_the_data_covers_is_fully_covered(self):
        self.assertEqual(reached("Source", WEEK, date(2026, 11, 2)), Coverage(WEEK))

    def test_a_requested_period_the_data_stops_inside_says_where(self):
        self.assertEqual(
            reached("Source", WEEK, date(2026, 10, 29)),
            Coverage(WEEK, date(2026, 10, 29)),
        )

    def test_a_requested_period_the_data_does_not_reach_is_unavailable(self):
        self.assertEqual(
            reached("Source", WEEK, date(2026, 10, 25)), Unavailable("Source", WEEK)
        )

    def test_data_that_does_not_exist_reaches_nothing(self):
        self.assertEqual(reached("Source", WEEK, None), Unavailable("Source", WEEK))

    def test_with_no_period_it_is_the_newest_week_ending_by_the_data(self):
        self.assertEqual(reached("Source", None, date(2026, 11, 3)), Coverage(WEEK))

    def test_with_no_period_and_data_ending_midweek_it_is_the_week_before(self):
        self.assertEqual(
            reached("Source", None, date(2026, 10, 29)),
            Coverage(Period(date(2026, 10, 19), date(2026, 10, 25))),
        )


if __name__ == "__main__":
    unittest.main()
