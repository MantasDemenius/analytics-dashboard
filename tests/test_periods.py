import unittest
from datetime import date

from weekly_report.periods import Period, week_ending_by


class WeekEndingByTest(unittest.TestCase):
    def test_on_a_sunday_that_week_is_complete(self):
        self.assertEqual(
            week_ending_by(date(2026, 11, 1)),
            Period(date(2026, 10, 26), date(2026, 11, 1)),
        )

    def test_midweek_picks_the_week_before(self):
        self.assertEqual(
            week_ending_by(date(2026, 10, 29)),
            Period(date(2026, 10, 19), date(2026, 10, 25)),
        )

    def test_on_a_monday_picks_the_week_ending_the_day_before(self):
        self.assertEqual(
            week_ending_by(date(2026, 11, 2)),
            Period(date(2026, 10, 26), date(2026, 11, 1)),
        )

    def test_on_a_saturday_picks_the_week_before(self):
        self.assertEqual(
            week_ending_by(date(2026, 10, 31)),
            Period(date(2026, 10, 19), date(2026, 10, 25)),
        )


class PeriodTest(unittest.TestCase):
    def test_previous_is_the_same_length_just_before(self):
        period = Period(date(2026, 10, 26), date(2026, 11, 1))
        self.assertEqual(
            period.previous(), Period(date(2026, 10, 19), date(2026, 10, 25))
        )

    def test_previous_of_an_uneven_range(self):
        period = Period(date(2026, 3, 1), date(2026, 3, 3))
        self.assertEqual(
            period.previous(), Period(date(2026, 2, 26), date(2026, 2, 28))
        )

    def test_days_are_inclusive(self):
        period = Period(date(2026, 10, 30), date(2026, 11, 1))
        self.assertEqual(
            period.days(),
            [date(2026, 10, 30), date(2026, 10, 31), date(2026, 11, 1)],
        )

    def test_a_single_day(self):
        period = Period(date(2026, 10, 30), date(2026, 10, 30))
        self.assertEqual(period.days(), [date(2026, 10, 30)])
        self.assertEqual(
            period.previous(), Period(date(2026, 10, 29), date(2026, 10, 29))
        )

    def test_months_within_one_month(self):
        period = Period(date(2026, 10, 5), date(2026, 10, 11))
        self.assertEqual(period.months(), [date(2026, 10, 1)])

    def test_months_of_a_week_straddling_two_months(self):
        period = Period(date(2026, 10, 26), date(2026, 11, 1))
        self.assertEqual(period.months(), [date(2026, 10, 1), date(2026, 11, 1)])

    def test_months_across_a_year_end(self):
        period = Period(date(2025, 12, 29), date(2026, 1, 4))
        self.assertEqual(period.months(), [date(2025, 12, 1), date(2026, 1, 1)])

    def test_label_within_one_year(self):
        period = Period(date(2026, 10, 26), date(2026, 11, 1))
        self.assertEqual(period.label(), "26 Oct to 1 Nov 2026")

    def test_label_across_a_year_end(self):
        period = Period(date(2025, 12, 29), date(2026, 1, 4))
        self.assertEqual(period.label(), "29 Dec 2025 to 4 Jan 2026")

    def test_end_before_start_is_refused(self):
        with self.assertRaises(ValueError):
            Period(date(2026, 11, 2), date(2026, 11, 1))


if __name__ == "__main__":
    unittest.main()
